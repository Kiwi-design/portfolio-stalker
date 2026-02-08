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
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def yahoo_meta(symbol, date=None):
    url = f"{YAHOO_BASES[0]}{symbol}?interval=1d&range=1d"
    if date:
        ts = int(datetime.strptime(date, "%Y-%m-%d").timestamp())
        url += f"&period1={ts}&period2={ts + 86400}"

    data = fetch_json(url, {"User-Agent": UA})
    res = data["chart"]["result"][0]
    return res["meta"]


def eur_to_ccy_on_date(ccy, date):
    if ccy == "EUR":
        return 1.0
    fx = yahoo_meta(f"EUR{ccy}=X", date)
    rate = fx.get("regularMarketPrice")
    return float(rate) if rate else None


def ccy_to_eur_today(ccy):
    if ccy == "EUR":
        return 1.0
    fx = yahoo_meta(f"EUR{ccy}=X")
    rate = fx.get("regularMarketPrice")
    return 1.0 / float(rate) if rate else None


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send(401, {"status": "error", "message": "Missing token"})
            return

        token = auth.replace("Bearer ", "")
        supabase_url = os.environ["SUPABASE_URL"]
        service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

        # Validate user
        user = fetch_json(
            f"{supabase_url}/auth/v1/user",
            {
                "Authorization": f"Bearer {token}",
                "apikey": service_key,
            },
        )
        user_id = user["id"]

        # Fetch transactions
        txs = fetch_json(
            f"{supabase_url}/rest/v1/transactions?user_id=eq.{user_id}&select=symbol,side,quantity,price,txn_date",
            {
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
        )

        # Average-cost (native currency)
        qty = {}
        cost_native = {}

        for t in sorted(txs, key=lambda x: x["txn_date"]):
            sym = t["symbol"].upper()
            side = t["side"]
            q = float(t["quantity"])
            price_eur = float(t["price"])
            d = t["txn_date"]

            meta = yahoo_meta(sym, d)
            ccy = meta["currency"]

            if ccy == "GBp":
                ccy = "GBP"

            fx = eur_to_ccy_on_date(ccy, d)
            price_native = price_eur * fx

            qty.setdefault(sym, 0.0)
            cost_native.setdefault(sym, 0.0)

            if side == "BUY":
                qty[sym] += q
                cost_native[sym] += q * price_native
            else:
                avg = cost_native[sym] / qty[sym]
                qty[sym] -= q
                cost_native[sym] -= q * avg

        results = []
        performance = []
        total_unrealized_eur = 0.0
        total_cost_eur = 0.0

        for sym, q in qty.items():
            if q <= 0:
                continue

            meta = yahoo_meta(sym)
            price_now = meta["regularMarketPrice"]
            ccy = meta["currency"]

            if ccy == "GBp":
                price_now /= 100
                ccy = "GBP"

            avg_cost_native = cost_native[sym] / q
            unreal_native = (price_now - avg_cost_native) * q

            fx_today = ccy_to_eur_today(ccy)
            unreal_eur = unreal_native * fx_today
            cost_eur = cost_native[sym] * fx_today

            total_unrealized_eur += unreal_eur
            total_cost_eur += cost_eur

            performance.append({
                "symbol": sym,
                "name": meta.get("shortName"),
                "quantity": q,
                "avg_cost": avg_cost_native,
                "current_price": price_now,
                "currency": ccy,
                "unrealized_eur": unreal_eur,
                "percent_unrealized": (price_now / avg_cost_native - 1) * 100
            })

            results.append({
                "symbol": sym,
                "name": meta.get("shortName"),
                "price": price_now,
                "currency": ccy,
                "quantity": q,
                "value_eur": q * price_now * fx_today
            })

        self._send(200, {
            "status": "ok",
            "results": results,
            "performance": performance,
            "performance_totals": {
                "total_unrealized_eur": total_unrealized_eur,
                "total_percent": (total_unrealized_eur / total_cost_eur) * 100 if total_cost_eur else 0
            }
        })
