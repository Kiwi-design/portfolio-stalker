from http.server import BaseHTTPRequestHandler
import os
import json
from urllib.request import Request, urlopen
from datetime import datetime

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

YAHOO_BASES = [
    "https://query1.finance.yahoo.com/v8/finance/chart/",
    "https://query2.finance.yahoo.com/v8/finance/chart/",
]


def _json_bytes(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


def _fetch_json(url: str, headers: dict, timeout: int = 15):
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_yahoo_chart(symbol: str):
    last_err = None
    for base in YAHOO_BASES:
        url = f"{base}{symbol}?interval=1d&range=1d"
        try:
            return _fetch_json(url, {"User-Agent": UA, "Accept": "application/json"}, timeout=10)
        except Exception as e:
            last_err = e
    raise last_err


def _get_meta_from_yahoo(symbol: str):
    data = _fetch_yahoo_chart(symbol)
    chart = data.get("chart", {})
    if chart.get("error"):
        raise Exception(f"Yahoo error for {symbol}: {chart['error']}")
    res0 = (chart.get("result") or [None])[0]
    if not res0:
        raise Exception(f"Yahoo missing result for {symbol}")
    return res0.get("meta", {})


def _parse_date(d: str):
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, obj: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()
        self.wfile.write(_json_bytes(obj))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send(401, {"status": "error", "message": "Missing Authorization: Bearer <token>"})
            return
        token = auth.replace("Bearer ", "", 1).strip()

        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

        if not supabase_url or not service_key:
            self._send(500, {"status": "error", "message": "Server misconfigured: missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY"})
            return

        # 1) Verify token and get user_id
        try:
            user = _fetch_json(
                f"{supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": service_key,
                    "Accept": "application/json",
                },
                timeout=10
            )
            user_id = user.get("id")
            email = user.get("email")
            if not user_id:
                self._send(401, {"status": "error", "message": "Invalid session token"})
                return
        except Exception as e:
            self._send(401, {"status": "error", "message": f"Auth verification failed: {str(e)}"})
            return

        # 2) Fetch transactions
        try:
            tx_url = f"{supabase_url}/rest/v1/transactions?user_id=eq.{user_id}&select=symbol,side,quantity,price,txn_date,created_at"
            txs = _fetch_json(
                tx_url,
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                    "Accept": "application/json",
                },
                timeout=10
            )
        except Exception as e:
            self._send(502, {"status": "error", "message": f"Failed to load transactions: {str(e)}"})
            return

        # Normalize + sort txs
        norm_txs = []
        for t in txs:
            sym = str(t.get("symbol", "")).strip().upper()
            side = str(t.get("side", "")).strip().upper()
            qty = float(t.get("quantity") or 0)
            price = float(t.get("price") or 0)
            d = _parse_date(str(t.get("txn_date") or ""))
            created_at = str(t.get("created_at") or "")
            if not sym or side not in ("BUY", "SELL") or qty <= 0 or price <= 0 or not d:
                continue
            norm_txs.append({
                "symbol": sym,
                "side": side,
                "quantity": qty,
                "price": price,
                "txn_date": d,
                "created_at": created_at,
            })

        norm_txs.sort(key=lambda x: (x["txn_date"], x["created_at"], x["symbol"]))

        # 3) Avg-cost method for remaining position
        positions_qty = {}
        positions_cost_basis = {}

        for t in norm_txs:
            sym = t["symbol"]
            side = t["side"]
            q = t["quantity"]
            p = t["price"]

            positions_qty.setdefault(sym, 0.0)
            positions_cost_basis.setdefault(sym, 0.0)

            if side == "BUY":
                positions_qty[sym] += q
                positions_cost_basis[sym] += q * p
            else:
                current_qty = positions_qty[sym]
                if current_qty <= 1e-12:
                    continue
                avg_cost = positions_cost_basis[sym] / current_qty
                sell_qty = min(q, current_qty)
                positions_qty[sym] -= sell_qty
                positions_cost_basis[sym] -= avg_cost * sell_qty

        symbols = [s for s, q in positions_qty.items() if abs(q) > 1e-12]

        # 4) FX: return CCY -> EUR conversion factor
        # Yahoo "EURUSD=X" is USD per 1 EUR.
        # To convert USD -> EUR, we must DIVIDE by that quote => multiply by 1/quote.
        fx_cache = {}  # ccy -> ccy_to_eur

        def ccy_to_eur_factor(ccy: str):
            if ccy == "EUR":
                return 1.0
            if ccy in fx_cache:
                return fx_cache[ccy]

            fx_sym = f"EUR{ccy}=X"  # quote: CCY per 1 EUR
            try:
                meta = _get_meta_from_yahoo(fx_sym)
                eur_to_ccy = meta.get("regularMarketPrice")
                if eur_to_ccy is None:
                    fx_cache[ccy] = None
                    return None
                eur_to_ccy = float(eur_to_ccy)
                if eur_to_ccy <= 1e-12:
                    fx_cache[ccy] = None
                    return None

                # invert: CCY -> EUR
                fx_cache[ccy] = 1.0 / eur_to_ccy
                return fx_cache[ccy]
            except Exception:
                fx_cache[ccy] = None
                return None

        results = []
        performance = []
        errors = []

        total_unrealized_eur = 0.0
        total_cost_basis_eur = 0.0

        for sym in symbols:
            qty = positions_qty.get(sym, 0.0)
            cost_basis = positions_cost_basis.get(sym, 0.0)

            try:
                meta = _get_meta_from_yahoo(sym)

                name = meta.get("shortName") or meta.get("longName")
                price = meta.get("regularMarketPrice")
                ccy = meta.get("currency")
                exch = meta.get("exchangeName")

                # Normalize GBp -> GBP (divide price by 100)
                if ccy == "GBp":
                    price = (float(price) / 100) if price is not None else None
                    ccy = "GBP"

                price_f = float(price) if price is not None else None
                value = price_f * qty if price_f is not None else None

                factor = ccy_to_eur_factor(ccy) if ccy else None
                value_eur = (value * factor) if (value is not None and factor is not None) else None

                # Portfolio row
                results.append({
                    "symbol": sym,
                    "name": name,
                    "price": price_f,
                    "currency": ccy,
                    "quantity": qty,
                    "value": value,
                    "value_eur": value_eur,
                    "exchange": exch,
                })

                # Performance row
                if qty > 1e-12 and price_f is not None:
                    avg_cost = cost_basis / qty if qty else None
                    unrealized_native = (price_f - avg_cost) * qty if avg_cost is not None else None

                    cost_basis_eur = (cost_basis * factor) if (factor is not None) else None
                    unrealized_eur = (unrealized_native * factor) if (unrealized_native is not None and factor is not None) else None

                    percent_unrealized = None
                    if avg_cost and avg_cost > 1e-12:
                        percent_unrealized = (price_f / avg_cost - 1.0) * 100.0

                    if unrealized_eur is not None:
                        total_unrealized_eur += unrealized_eur
                    if cost_basis_eur is not None:
                        total_cost_basis_eur += cost_basis_eur

                    performance.append({
                        "symbol": sym,
                        "name": name,
                        "currency": ccy,
                        "quantity": qty,
                        "avg_cost": avg_cost,
                        "current_price": price_f,
                        "unrealized_native": unrealized_native,
                        "unrealized_eur": unrealized_eur,
                        "percent_unrealized": percent_unrealized,
                        "cost_basis_native": cost_basis,
                        "cost_basis_eur": cost_basis_eur,
                    })

            except Exception as e:
                errors.append({"symbol": sym, "message": str(e)})

        total_percent = 0.0
        if total_cost_basis_eur > 1e-12:
            total_percent = (total_unrealized_eur / total_cost_basis_eur) * 100.0

        self._send(200, {
            "status": "ok",
            "user": {"id": user_id, "email": email},

            "results": results,
            "errors": errors,

            "performance": performance,
            "performance_totals": {
                "total_unrealized_eur": total_unrealized_eur,
                "total_cost_basis_eur": total_cost_basis_eur,
                "total_percent": total_percent,
            }
        })
