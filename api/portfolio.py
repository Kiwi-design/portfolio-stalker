from http.server import BaseHTTPRequestHandler
import os, json
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


def fetch_json(url, headers):
    req = Request(url, headers=headers)
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def yahoo_meta(symbol, date=None):
    # If date is provided, query a 1-day window around that date for a close/price.
    base = YAHOO_BASES[0]
    url = f"{base}{symbol}?interval=1d&range=1d"

    if date:
        ts = int(datetime.strptime(date, "%Y-%m-%d").timestamp())
        url = f"{base}{symbol}?interval=1d&period1={ts}&period2={ts + 86400}"

    data = fetch_json(url, {"User-Agent": UA, "Accept": "application/json"})
    chart = data.get("chart", {})
    if chart.get("error"):
        raise Exception(str(chart["error"]))

    res0 = (chart.get("result") or [None])[0]
    if not res0:
        raise Exception(f"Yahoo missing result for {symbol}")

    meta = res0.get("meta") or {}
    return meta


def eur_to_ccy_on_date(ccy, date):
    # returns EUR -> CCY factor at that date
    if ccy == "EUR":
        return 1.0
    fx = yahoo_meta(f"EUR{ccy}=X", date)
    rate = fx.get("regularMarketPrice")
    return float(rate) if rate else None


def ccy_to_eur_today(ccy):
    # returns CCY -> EUR factor today
    if ccy == "EUR":
        return 1.0
    fx = yahoo_meta(f"EUR{ccy}=X")
    rate = fx.get("regularMarketPrice")
    return (1.0 / float(rate)) if rate else None


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def _send(self, code, obj):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))

    def do_OPTIONS(self):
        # CORS preflight
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        try:
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                self._send(401, {"status": "error", "message": "Missing Authorization: Bearer <token>"})
                return

            token = auth.replace("Bearer ", "", 1).strip()

            supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
            service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

            if not supabase_url or not service_key:
                self._send(500, {"status": "error", "message": "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY"})
                return

            # Validate user
            user = fetch_json(
                f"{supabase_url}/auth/v1/user",
                {
                    "Authorization": f"Bearer {token}",
                    "apikey": service_key,
                    "Accept": "application/json",
                },
            )
            user_id = user.get("id")
            email = user.get("email")
            if not user_id:
                self._send(401, {"status": "error", "message": "Invalid session"})
                return

            # Fetch transactions (price is in EUR per your rule)
            txs = fetch_json(
                f"{supabase_url}/rest/v1/transactions?user_id=eq.{user_id}&select=symbol,side,quantity,price,txn_date,created_at",
                {
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                    "Accept": "application/json",
                },
            )

            # Normalize and sort by date then created_at
            norm = []
            for t in txs:
                sym = str(t.get("symbol", "")).strip().upper()
                side = str(t.get("side", "")).strip().upper()
                q = float(t.get("quantity") or 0)
                price_eur = float(t.get("price") or 0)
                d = str(t.get("txn_date") or "")
                created_at = str(t.get("created_at") or "")

                if not sym or side not in ("BUY", "SELL") or q <= 0 or price_eur <= 0 or not d:
                    continue

                norm.append({
                    "symbol": sym,
                    "side": side,
                    "quantity": q,
                    "price_eur": price_eur,
                    "txn_date": d,
                    "created_at": created_at,
                })

            norm.sort(key=lambda x: (x["txn_date"], x["created_at"], x["symbol"]))

            # Average cost method in NATIVE currency, but trades entered in EUR:
            qty = {}
            cost_native = {}
            asset_ccy = {}  # symbol -> currency (from yahoo at trade time)

            for t in norm:
                sym = t["symbol"]
                side = t["side"]
                q = t["quantity"]
                price_eur = t["price_eur"]
                d = t["txn_date"]

                meta_trade = yahoo_meta(sym, d)
                ccy = meta_trade.get("currency")

                # handle GBp instruments: treat currency as GBP for FX and prices
                if ccy == "GBp":
                    ccy = "GBP"

                asset_ccy[sym] = ccy

                fx_eur_to_ccy = eur_to_ccy_on_date(ccy, d)
                if fx_eur_to_ccy is None:
                    raise Exception(f"Missing FX EUR->{ccy} for {d}")

                price_native = price_eur * fx_eur_to_ccy

                qty.setdefault(sym, 0.0)
                cost_native.setdefault(sym, 0.0)

                if side == "BUY":
                    qty[sym] += q
                    cost_native[sym] += q * price_native
                else:
                    # sell reduces at current avg cost
                    if qty[sym] <= 1e-12:
                        continue
                    avg = cost_native[sym] / qty[sym]
                    sell_q = min(q, qty[sym])
                    qty[sym] -= sell_q
                    cost_native[sym] -= sell_q * avg

            results = []
            performance = []
            errors = []

            total_unrealized_eur = 0.0
            total_cost_eur = 0.0

            for sym, q in qty.items():
                if q <= 1e-12:
                    continue

                meta_now = yahoo_meta(sym)
                ccy = meta_now.get("currency")
                price_now = meta_now.get("regularMarketPrice")
                name = meta_now.get("shortName") or meta_now.get("longName")

                if ccy == "GBp":
                    # Yahoo price is in pence; convert to pounds
                    price_now = float(price_now) / 100.0 if price_now is not None else None
                    ccy = "GBP"

                if price_now is None:
                    errors.append({"symbol": sym, "message": "Missing current price"})
                    continue

                price_now = float(price_now)
                avg_cost_native = cost_native[sym] / q

                unreal_native = (price_now - avg_cost_native) * q

                fx_ccy_to_eur = ccy_to_eur_today(ccy)
                if fx_ccy_to_eur is None:
                    errors.append({"symbol": sym, "message": f"Missing FX {ccy}->EUR"})
                    continue

                unreal_eur = unreal_native * fx_ccy_to_eur
                cost_eur = cost_native[sym] * fx_ccy_to_eur

                total_unrealized_eur += unreal_eur
                total_cost_eur += cost_eur

                # portfolio value (EUR)
                value_eur = (q * price_now) * fx_ccy_to_eur

                results.append({
                    "symbol": sym,
                    "name": name,
                    "price": price_now,
                    "currency": ccy,
                    "quantity": q,
                    "value": q * price_now,
                    "value_eur": value_eur,
                })

                performance.append({
                    "symbol": sym,
                    "name": name,
                    "quantity": q,
                    "avg_cost": avg_cost_native,
                    "current_price": price_now,
                    "currency": ccy,
                    "unrealized_eur": unreal_eur,
                    "percent_unrealized": (price_now / avg_cost_native - 1.0) * 100.0 if avg_cost_native > 1e-12 else 0.0,
                })

            total_percent = (total_unrealized_eur / total_cost_eur) * 100.0 if total_cost_eur > 1e-12 else 0.0

            self._send(200, {
                "status": "ok",
                "user": {"id": user_id, "email": email},
                "results": results,
                "performance": performance,
                "performance_totals": {
                    "total_unrealized_eur": total_unrealized_eur,
                    "total_cost_basis_eur": total_cost_eur,
                    "total_percent": total_percent,
                },
                "errors": errors,
            })

        except Exception as e:
            # return JSON error instead of crashing (also includes CORS)
            self._send(502, {"status": "error", "message": f"Upstream failed: {str(e)}"})
