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


def fetch_json(url, headers, timeout=20):
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def yahoo_meta(symbol, date=None):
    # If date is provided, query a 1-day window around that date.
    base = YAHOO_BASES[0]
    if date:
        ts = int(datetime.strptime(date, "%Y-%m-%d").timestamp())
        url = f"{base}{symbol}?interval=1d&period1={ts}&period2={ts + 86400}"
    else:
        url = f"{base}{symbol}?interval=1d&range=1d"

    data = fetch_json(url, {"User-Agent": UA, "Accept": "application/json"})
    chart = data.get("chart", {})
    if chart.get("error"):
        raise Exception(str(chart["error"]))

    res0 = (chart.get("result") or [None])[0]
    if not res0:
        raise Exception(f"Yahoo missing result for {symbol}")
    return res0.get("meta") or {}


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

            # Verify user
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

            # Load transactions (prices are in EUR per your rule)
            txs = fetch_json(
                f"{supabase_url}/rest/v1/transactions?user_id=eq.{user_id}&select=symbol,side,quantity,price,txn_date,created_at",
                {
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                    "Accept": "application/json",
                },
            )

            # Normalize and sort by txn_date then created_at
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

            # FX caches
            eur_to_ccy_cache = {}        # (ccy, date) -> EUR->CCY
            ccy_to_eur_date_cache = {}   # (ccy, date) -> CCY->EUR
            ccy_to_eur_today_cache = {}  # ccy -> CCY->EUR today

            def normalize_ccy(ccy: str):
                # Treat GBp as GBP for FX and for arithmetic (pence->pounds handled for live prices)
                return "GBP" if ccy == "GBp" else ccy

            def eur_to_ccy_on_date(ccy: str, date: str):
                # returns EUR -> CCY factor at date
                ccy = normalize_ccy(ccy)
                if ccy == "EUR":
                    return 1.0
                key = (ccy, date)
                if key in eur_to_ccy_cache:
                    return eur_to_ccy_cache[key]
                fx_meta = yahoo_meta(f"EUR{ccy}=X", date)
                rate = fx_meta.get("regularMarketPrice")
                eur_to_ccy_cache[key] = float(rate) if rate else None
                return eur_to_ccy_cache[key]

            def ccy_to_eur_on_date(ccy: str, date: str):
                # returns CCY -> EUR factor at date (inverse of EURCCY)
                ccy = normalize_ccy(ccy)
                if ccy == "EUR":
                    return 1.0
                key = (ccy, date)
                if key in ccy_to_eur_date_cache:
                    return ccy_to_eur_date_cache[key]
                eur_to_ccy = eur_to_ccy_on_date(ccy, date)
                if eur_to_ccy is None or eur_to_ccy <= 1e-12:
                    ccy_to_eur_date_cache[key] = None
                else:
                    ccy_to_eur_date_cache[key] = 1.0 / eur_to_ccy
                return ccy_to_eur_date_cache[key]

            def ccy_to_eur_today(ccy: str):
                ccy = normalize_ccy(ccy)
                if ccy == "EUR":
                    return 1.0
                if ccy in ccy_to_eur_today_cache:
                    return ccy_to_eur_today_cache[ccy]
                fx_meta = yahoo_meta(f"EUR{ccy}=X")
                rate = fx_meta.get("regularMarketPrice")
                ccy_to_eur_today_cache[ccy] = (1.0 / float(rate)) if rate else None
                return ccy_to_eur_today_cache[ccy]

            # --- Average-cost tracking in NATIVE currency ---
            qty = {}            # symbol -> open qty
            cost_native = {}    # symbol -> open cost basis (native)
            realized_native = {}  # symbol -> realized profit (native), accumulated over SELLs

            # Cache asset trading currency (from Yahoo at transaction time)
            asset_ccy = {}  # symbol -> currency

            for t in norm:
                sym = t["symbol"]
                side = t["side"]
                q = t["quantity"]
                price_eur = t["price_eur"]
                d = t["txn_date"]

                # Determine asset currency at that date
                meta_trade = yahoo_meta(sym, d)
                ccy = normalize_ccy(meta_trade.get("currency"))
                if not ccy:
                    raise Exception(f"Missing currency for {sym} on {d}")
                asset_ccy[sym] = ccy

                # Convert EUR trade price to native currency at transaction date
                fx_eur_to_ccy = eur_to_ccy_on_date(ccy, d)
                if fx_eur_to_ccy is None:
                    raise Exception(f"Missing FX EUR->{ccy} on {d}")
                trade_price_native = price_eur * fx_eur_to_ccy

                qty.setdefault(sym, 0.0)
                cost_native.setdefault(sym, 0.0)
                realized_native.setdefault(sym, 0.0)

                if side == "BUY":
                    qty[sym] += q
                    cost_native[sym] += q * trade_price_native
                else:
                    # SELL: realized profit is (sell - avg_cost) * qty_sold in NATIVE currency
                    if qty[sym] <= 1e-12:
                        # selling without holdings - ignore
                        continue
                    avg_cost = cost_native[sym] / qty[sym]
                    sell_q = min(q, qty[sym])

                    realized_native[sym] += (trade_price_native - avg_cost) * sell_q

                    qty[sym] -= sell_q
                    cost_native[sym] -= avg_cost * sell_q

            # Build portfolio + performance
            results = []
            performance = []
            errors = []

            total_unrealized_eur = 0.0
            total_cost_basis_eur = 0.0
            total_realized_eur = 0.0

            for sym, q_open in qty.items():
                ccy = asset_ccy.get(sym)
                if not ccy:
                    # if no tx currency known, skip
                    continue

                # Realized(EUR): convert realized_native to EUR using a consistent approach
                # We convert each SELL at its date in the loop above by keeping realized in native,
                # but EUR needs an FX point. We will convert SELL-by-SELL at date would be ideal.
                #
                # To keep it correct, we should convert realized per SELL at the SELL date.
                # We did not store per-sell breakdown, so we will recompute realized EUR accurately
                # by replaying transactions again just for realized EUR (lightweight, uses cache).
                #
                # (This avoids incorrect conversion using today's FX.)
                pass

            # Recompute realized EUR accurately (SELL-by-SELL conversion at sale date)
            qty2 = {}
            cost2 = {}
            realized_eur = {}  # symbol -> realized in EUR

            for t in norm:
                sym = t["symbol"]
                side = t["side"]
                q = t["quantity"]
                price_eur = t["price_eur"]
                d = t["txn_date"]

                meta_trade = yahoo_meta(sym, d)
                ccy = normalize_ccy(meta_trade.get("currency"))
                if not ccy:
                    continue

                fx_eur_to_ccy = eur_to_ccy_on_date(ccy, d)
                fx_ccy_to_eur = ccy_to_eur_on_date(ccy, d)
                if fx_eur_to_ccy is None or fx_ccy_to_eur is None:
                    continue

                trade_price_native = price_eur * fx_eur_to_ccy

                qty2.setdefault(sym, 0.0)
                cost2.setdefault(sym, 0.0)
                realized_eur.setdefault(sym, 0.0)

                if side == "BUY":
                    qty2[sym] += q
                    cost2[sym] += q * trade_price_native
                else:
                    if qty2[sym] <= 1e-12:
                        continue
                    avg_cost = cost2[sym] / qty2[sym]
                    sell_q = min(q, qty2[sym])

                    realized_native_tx = (trade_price_native - avg_cost) * sell_q
                    realized_eur_tx = realized_native_tx * fx_ccy_to_eur  # convert at SELL date
                    realized_eur[sym] += realized_eur_tx

                    qty2[sym] -= sell_q
                    cost2[sym] -= avg_cost * sell_q

            # Now build open positions
            for sym, q_open in qty.items():
                if q_open <= 1e-12:
                    # no open position, but still could have realized P&L
                    continue

                try:
                    meta_now = yahoo_meta(sym)
                    name = meta_now.get("shortName") or meta_now.get("longName")
                    ccy_now = normalize_ccy(meta_now.get("currency"))
                    price_now = meta_now.get("regularMarketPrice")

                    if price_now is None:
                        errors.append({"symbol": sym, "message": "Missing current price"})
                        continue

                    price_now = float(price_now)

                    # Handle GBp live pricing: Yahoo may report pence as GBp
                    # If currency came as GBp we normalized to GBP; but price still needs /100.
                    # We detect original currency:
                    if meta_now.get("currency") == "GBp":
                        price_now = price_now / 100.0

                    fx_ccy_to_eur_now = ccy_to_eur_today(ccy_now)
                    if fx_ccy_to_eur_now is None:
                        errors.append({"symbol": sym, "message": f"Missing FX {ccy_now}->EUR (today)"})
                        continue

                    avg_cost_native = cost_native[sym] / q_open
                    unreal_native = (price_now - avg_cost_native) * q_open
                    unreal_eur = unreal_native * fx_ccy_to_eur_now

                    cost_basis_eur = cost_native[sym] * fx_ccy_to_eur_now
                    value_eur = (q_open * price_now) * fx_ccy_to_eur_now

                    total_unrealized_eur += unreal_eur
                    total_cost_basis_eur += cost_basis_eur
                    total_realized_eur += realized_eur.get(sym, 0.0)

                    results.append({
                        "symbol": sym,
                        "name": name,
                        "price": price_now,
                        "currency": ccy_now,
                        "quantity": q_open,
                        "value": q_open * price_now,
                        "value_eur": value_eur,
                    })

                    performance.append({
                        "symbol": sym,
                        "name": name,
                        "quantity": q_open,
                        "avg_cost": avg_cost_native,
                        "current_price": price_now,
                        "currency": ccy_now,
                        "unrealized_eur": unreal_eur,
                        "percent_unrealized": (price_now / avg_cost_native - 1.0) * 100.0 if avg_cost_native > 1e-12 else 0.0,
                        "realized_eur": realized_eur.get(sym, 0.0),
                    })

                except Exception as e:
                    errors.append({"symbol": sym, "message": str(e)})

            total_percent = (total_unrealized_eur / total_cost_basis_eur) * 100.0 if total_cost_basis_eur > 1e-12 else 0.0

            self._send(200, {
                "status": "ok",
                "user": {"id": user_id, "email": email},
                "results": results,
                "performance": performance,
                "performance_totals": {
                    "total_unrealized_eur": total_unrealized_eur,
                    "total_cost_basis_eur": total_cost_basis_eur,
                    "total_percent": total_percent,
                    "total_realized_eur": total_realized_eur,
                },
                "errors": errors,
            })

        except Exception as e:
            self._send(502, {"status": "error", "message": f"Upstream failed: {str(e)}"})
