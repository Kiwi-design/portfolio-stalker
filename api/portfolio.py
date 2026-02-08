from http.server import BaseHTTPRequestHandler
import os
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

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
        # ---- 1) Read bearer token ----
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

        # ---- 2) Verify token with Supabase and get user_id ----
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

        # ---- 3) Fetch transactions for this user from Supabase ----
        # Using service_role key to bypass RLS safely (we filter by user_id ourselves).
        try:
            # URL-encoded PostgREST filter: user_id=eq.<uuid>
            tx_url = f"{supabase_url}/rest/v1/transactions?user_id=eq.{user_id}&select=symbol,side,quantity,price,txn_date"
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

        # ---- 4) Compute net quantities per symbol ----
        positions = {}  # symbol -> qty
        for t in txs:
            sym = str(t.get("symbol", "")).strip().upper()
            side = str(t.get("side", "")).strip().upper()
            qty = float(t.get("quantity") or 0)

            if not sym or side not in ("BUY", "SELL"):
                continue

            positions.setdefault(sym, 0.0)
            if side == "BUY":
                positions[sym] += qty
            else:
                positions[sym] -= qty

        # Remove symbols with zero position
        symbols = [s for s, q in positions.items() if abs(q) > 1e-12]

        # ---- 5) Fetch prices + convert value to EUR ----
        results = []
        errors = []

        fx_cache = {}  # currency -> rate (EUR<ccy>=X)

        def fx_to_eur(ccy: str):
            if ccy == "EUR":
                return 1.0
            if ccy in fx_cache:
                return fx_cache[ccy]
            fx_sym = f"EUR{ccy}=X"
            try:
                meta = _get_meta_from_yahoo(fx_sym)
                rate = meta.get("regularMarketPrice")
                fx_cache[ccy] = float(rate) if rate is not None else None
                return fx_cache[ccy]
            except Exception:
                fx_cache[ccy] = None
                return None

        for sym in symbols:
            qty = positions.get(sym, 0.0)
            try:
                meta = _get_meta_from_yahoo(sym)

                name = meta.get("shortName") or meta.get("longName")
                price = meta.get("regularMarketPrice")
                ccy = meta.get("currency")
                exch = meta.get("exchangeName")

                # Normalize GBp -> GBP
                if ccy == "GBp":
                    price = (float(price) / 100) if price is not None else None
                    ccy = "GBP"

                price_f = float(price) if price is not None else None
                value = price_f * qty if price_f is not None else None

                rate = fx_to_eur(ccy) if ccy else None
                value_eur = (value * rate) if (value is not None and rate is not None) else None

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
            except Exception as e:
                errors.append({"symbol": sym, "message": str(e)})

        self._send(200, {
            "status": "ok",
            "user": {"id": user_id, "email": email},
            "results": results,
            "errors": errors,
        })

