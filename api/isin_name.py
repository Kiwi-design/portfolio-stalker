from http.server import BaseHTTPRequestHandler
import json
import os
import re
from html import unescape
from urllib.parse import quote_plus, parse_qs, urlparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor
import http.cookiejar

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
ISIN_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{10}\b")
INVALID_NAME_VALUES = {"", "null", "none", "n/a", "na", "undefined", "-"}
BASE_DOMAIN = "https://www.wealthmanagement.bnpparibas.de"
YAHOO_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"

_BNP_COOKIE_JAR = http.cookiejar.CookieJar()
_BNP_OPENER = build_opener(HTTPCookieProcessor(_BNP_COOKIE_JAR))
_BNP_PRIMED = False


def fetch_text(url, headers=None, timeout=25):
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url, headers=None, timeout=25):
    return json.loads(fetch_text(url, headers=headers, timeout=timeout))




def bnp_fetch_text(url, headers=None, timeout=25):
    req = Request(url, headers=headers or {})
    with _BNP_OPENER.open(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def prime_bnp_session():
    global _BNP_PRIMED
    if _BNP_PRIMED:
        return
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        bnp_fetch_text(f"{BASE_DOMAIN}/web/home", headers=headers, timeout=20)
    except Exception:
        pass
    # best-effort cookie bootstrap used by marketdata endpoints
    try:
        bnp_fetch_text(
            f"{BASE_DOMAIN}/web-sec-service/api/cookie/content",
            headers={"User-Agent": UA, "Accept": "application/json", "Referer": f"{BASE_DOMAIN}/web/home"},
            timeout=20,
        )
    except Exception:
        pass
    _BNP_PRIMED = True


def bnp_fetch_json(url, headers=None, timeout=25):
    prime_bnp_session()
    return json.loads(bnp_fetch_text(url, headers=headers, timeout=timeout))

def read_str(record, keys):
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_isin(value):
    if not value:
        return ""
    m = ISIN_RE.search(str(value).upper())
    return m.group(0) if m else ""


def normalize_symbol(value):
    return str(value or "").strip().upper()


def normalize_name(value):
    if not value:
        return ""
    name = re.sub(r"\s+", " ", str(value)).strip()
    if name.lower() in INVALID_NAME_VALUES:
        return ""
    return name


def normalize_txn_close_price(value):
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.lower() in INVALID_NAME_VALUES or text.lower() == "unavailable":
        return ""
    return text


def normalize_currency_code(value):
    code = str(value or "").strip().upper()
    return code if re.fullmatch(r"[A-Z]{3}", code) else ""


def combine_close_and_currency(close_price, currency):
    price = normalize_txn_close_price(close_price)
    if not price:
        return ""
    code = normalize_currency_code(currency)
    return f"{price} {code}" if code else price




def extract_currency_from_close_text(value):
    text = normalize_txn_close_price(value)
    if not text:
        return ""
    m = re.search(r"\b([A-Z]{3})$", text)
    return normalize_currency_code(m.group(1) if m else "")

def txn_date_older_than_12m(txn_date):
    try:
        d = datetime.strptime(txn_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return False
    return (datetime.now(timezone.utc) - d).days > 366


def normalize_payload_date(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:10], fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)
    m = re.search(r"(\d{2})[./-](\d{2})[./-](\d{4})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return ""


def yahoo_chart(symbol, params):
    query = "&".join([f"{k}={quote_plus(str(v))}" for k, v in params.items()])
    url = f"{YAHOO_CHART_BASE}{quote_plus(symbol)}?{query}"
    return fetch_json(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
        },
    )


def yahoo_symbol_name(symbol):
    try:
        payload = yahoo_chart(symbol, {"interval": "1d", "range": "5d"})
    except Exception:
        return ""
    res0 = ((payload or {}).get("chart", {}).get("result") or [None])[0] or {}
    meta = res0.get("meta") or {}
    name = meta.get("shortName") or meta.get("longName") or ""
    return normalize_name(name)




def yahoo_symbol_for_isin(isin):
    try:
        payload = fetch_json(
            f"{YAHOO_SEARCH_URL}?q={quote_plus(isin)}",
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=20,
        )
    except Exception:
        return "", ""

    quotes = payload.get("quotes") or []
    best_symbol = ""
    best_name = ""

    for q in quotes:
        if not isinstance(q, dict):
            continue
        symbol = normalize_symbol(q.get("symbol"))
        if not symbol:
            continue
        name = normalize_name(q.get("shortname") or q.get("longname") or q.get("quoteType") or "")
        q_isin = normalize_isin(q.get("isin") or "")
        if q_isin == isin:
            return symbol, name
        if not best_symbol:
            best_symbol = symbol
            best_name = name

    return best_symbol, best_name

def yahoo_closing_quote_for_symbol_date(symbol, txn_date):
    if not txn_date:
        return "", ""
    try:
        target = datetime.strptime(txn_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return "unavailable", ""

    start_ts = int((target - timedelta(days=7)).timestamp())
    end_ts = int((target + timedelta(days=2)).timestamp())

    try:
        payload = yahoo_chart(symbol, {
            "interval": "1d",
            "period1": start_ts,
            "period2": end_ts,
        })
    except Exception:
        return "unavailable", ""

    res0 = ((payload or {}).get("chart", {}).get("result") or [None])[0] or {}
    currency = normalize_currency_code(((res0.get("meta") or {}).get("currency")))
    timestamps = res0.get("timestamp") or []
    quote0 = ((res0.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote0.get("close") or []

    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((d, float(close)))

    if not rows:
        return "unavailable", currency

    # Prefer exact date; otherwise use the nearest prior market close.
    exact = [v for d, v in rows if d == txn_date]
    if exact:
        return f"{exact[0]:.4f}", currency

    prior = [(d, v) for d, v in rows if d <= txn_date]
    if prior:
        return f"{sorted(prior, key=lambda x: x[0])[-1][1]:.4f}", currency

    return "unavailable", currency


def yahoo_closing_price_for_symbol_date(symbol, txn_date):
    price, _ = yahoo_closing_quote_for_symbol_date(symbol, txn_date)
    return price


def maybe_parse_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    text = text.replace("%", "")
    if text.count(",") == 1 and text.count(".") >= 1:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except Exception:
        return None


def iter_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_dicts(v)


def extract_close_value_from_json_obj(obj, txn_date):
    date_keys = ("date", "datum", "tradingDate", "tradeDate", "valuationDate")
    close_keys = ("close", "closePrice", "closing", "nav", "last", "price", "kurs", "schlusskurs")
    d = ""
    for k in date_keys:
        if k in obj:
            d = normalize_payload_date(obj.get(k))
            if d:
                break
    if d != txn_date:
        return None
    for k in close_keys:
        if k in obj:
            val = maybe_parse_float(obj.get(k))
            if val is not None:
                return val
    return None


def historical_prices_url_from_security_url(security_url):
    if not security_url:
        return ""
    base = security_url.rstrip("/")
    if base.endswith("/Kurse-und-Handelsplaetze/Historische-Kurse"):
        return base
    return f"{base}/Kurse-und-Handelsplaetze/Historische-Kurse"


def ajax_price_endpoints_from_historical_url(hist_url, page):
    candidates = []
    templates = [x.strip() for x in os.environ.get("BNP_WM_CLOSE_AJAX_URLS", "").split(",") if x.strip()]
    for t in templates:
        candidates.append(
            t.replace("{history_url}", hist_url).replace("{page}", str(page))
        )

    tail_patterns = [
        f"{hist_url}/_jcr_content/historicalpricechanges.ajax.json?page={page}",
        f"{hist_url}/_jcr_content/historicalpricechanges.json?page={page}",
        f"{hist_url}/_jcr_content/historicalPrices.ajax.json?page={page}",
        f"{hist_url}/_jcr_content/historicalPrices.json?page={page}",
        f"{hist_url}.ajax.json?page={page}",
        f"{hist_url}.json?page={page}",
    ]
    candidates.extend(tail_patterns)
    return candidates


def discover_ajax_template_from_history_page(hist_url):
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Referer": f"{BASE_DOMAIN}/web/home",
    }
    try:
        html = fetch_text(hist_url, headers=headers)
    except Exception:
        return ""

    m = re.search(r"((?:https?:\\/\\/|\\/)[^\"']*histor[^\"']*ajax[^\"']*json[^\"']*)", html, flags=re.IGNORECASE)
    if not m:
        return ""
    url = unescape(m.group(1)).replace("\/", "/")
    url = to_absolute_url(url)
    if "{page}" in url:
        return url
    if "page=" in url:
        return re.sub(r"page=\d+", "page={page}", url)
    glue = "&" if "?" in url else "?"
    return f"{url}{glue}page={{page}}"


def find_closing_price_via_ajax(history_url, txn_date):
    headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Referer": history_url,
    }
    page_limit = int(os.environ.get("BNP_WM_CLOSE_PAGE_LIMIT", "80"))

    discovered_template = discover_ajax_template_from_history_page(history_url)

    for page in range(0, page_limit):
        page_urls = []
        if discovered_template:
            page_urls.append(discovered_template.replace("{page}", str(page)))
        page_urls.extend(ajax_price_endpoints_from_historical_url(history_url, page))

        seen = set()
        page_found_any = False
        for url in page_urls:
            if url in seen:
                continue
            seen.add(url)
            try:
                payload_text = fetch_text(url, headers=headers)
            except Exception:
                continue
            page_found_any = True

            # JSON path first
            try:
                payload_json = json.loads(payload_text)
                for obj in iter_dicts(payload_json):
                    val = extract_close_value_from_json_obj(obj, txn_date)
                    if val is not None:
                        return f"{val:.4f}"
            except Exception:
                pass

            # Text fallback
            d = re.escape(txn_date)
            patterns = [
                rf"{d}[^\n\r]{{0,180}}(?:close|closing|closePrice|price|nav|kurs|schlusskurs)\"?\s*[:=]\s*\"?([0-9]+(?:[\\.,][0-9]+)?)",
                rf"(?:close|closing|closePrice|price|nav|kurs|schlusskurs)\"?\s*[:=]\s*\"?([0-9]+(?:[\\.,][0-9]+)?)[^\n\r]{{0,180}}{d}",
            ]
            for pattern in patterns:
                m = re.search(pattern, payload_text, flags=re.IGNORECASE)
                if m:
                    val = maybe_parse_float(m.group(1))
                    if val is not None:
                        return f"{val:.4f}"

        # if no endpoint responded on first page at all, likely wrong endpoint family
        if page == 0 and not page_found_any and not discovered_template:
            continue
        # if none responded for later pages, stop paging
        if page > 0 and not page_found_any:
            break

    return "unavailable"




def bnp_marketdata_history_close_for_isin_date(isin, txn_date):
    headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        "Referer": f"{BASE_DOMAIN}/web/home",
    }
    page_limit = int(os.environ.get("BNP_WM_CLOSE_PAGE_LIMIT", "80"))
    market_types = ["funds", "stocks", "bonds", "etfs", "certificates", "indices"]
    basic_fields = ["BasicV2", "BasicV1"]

    best_prior = None

    for market_type in market_types:
        exchanges = []
        for basic in basic_fields:
            meta_url = (
                f"{BASE_DOMAIN}/web-financialinfo-service/api/marketdata/{market_type}"
                f"?id={quote_plus(isin)}&field={basic}&field=ExchangesV2&field=ConditionsV1"
            )
            try:
                payload = bnp_fetch_json(meta_url, headers=headers)
            except Exception:
                continue
            if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
                continue
            exchanges = payload[0].get("ExchangesV2") or []
            if exchanges:
                break

        if not exchanges:
            continue

        for exchange in exchanges:
            consors_id = str(exchange.get("CONSORS_ID") or "").strip()
            if not consors_id:
                continue
            for page in range(0, page_limit):
                hist_url = (
                    f"{BASE_DOMAIN}/web-financialinfo-service/api/marketdata/{market_type}"
                    f"?id={quote_plus(consors_id)}&field=HistoryV1&page={page}&range=-5000&resolution=1D"
                )
                try:
                    hist_payload = bnp_fetch_json(hist_url, headers=headers)
                except Exception:
                    if page > 0:
                        break
                    continue
                if not isinstance(hist_payload, list) or not hist_payload or not isinstance(hist_payload[0], dict):
                    if page > 0:
                        break
                    continue
                items = (hist_payload[0].get("HistoryV1") or {}).get("ITEMS") or []
                if not items:
                    if page > 0:
                        break
                    continue

                for item in items:
                    item_date = normalize_payload_date(item.get("DATETIME_LAST") or item.get("date") or "")
                    if not item_date:
                        continue
                    close_val = maybe_parse_float(item.get("LAST"))
                    if close_val is None:
                        close_val = maybe_parse_float(item.get("close"))
                    if close_val is None:
                        continue

                    item_ccy = normalize_currency_code(item.get("ISO_CURRENCY"))

                    if item_date == txn_date:
                        return f"{close_val:.4f}", item_ccy

                    if item_date <= txn_date:
                        if best_prior is None or item_date > best_prior[0]:
                            best_prior = (item_date, close_val, item_ccy)

    if best_prior is not None:
        return f"{best_prior[1]:.4f}", best_prior[2]
    return "", ""

def bnp_closing_price_for_isin_date(isin, txn_date, security_url=""):
    if not txn_date:
        return "", ""
    direct, direct_ccy = bnp_marketdata_history_close_for_isin_date(isin, txn_date)
    if direct:
        return direct, direct_ccy

    base_url = security_url
    if not base_url:
        discovered = discover_security_url_for_isin(isin) or {}
        base_url = discovered.get("url", "")

    history_url = historical_prices_url_from_security_url(base_url)
    if history_url:
        parsed = find_closing_price_via_ajax(history_url, txn_date)
        if parsed and parsed != "unavailable":
            return parsed, ""

    y_symbol, _ = yahoo_symbol_for_isin(isin)
    if y_symbol:
        y_close, y_ccy = yahoo_closing_quote_for_symbol_date(y_symbol, txn_date)
        if y_close and y_close != "unavailable":
            return y_close, y_ccy

    return "unavailable", ""


def resolve_security_metadata(isin, txn_date=None):
    lookup = bnp_find_url_and_name_for_isin(isin)
    name = normalize_name((lookup or {}).get("name"))
    security_url = (lookup or {}).get("url", "")

    yahoo_symbol, yahoo_name = yahoo_symbol_for_isin(isin)
    if not name and yahoo_name:
        name = yahoo_name

    close_price, close_ccy = bnp_closing_price_for_isin_date(isin, txn_date, security_url=security_url) if txn_date else ("", "")
    if (not close_price or close_price == "unavailable") and txn_date and yahoo_symbol:
        close_price, close_ccy = yahoo_closing_quote_for_symbol_date(yahoo_symbol, txn_date)

    close_with_ccy = combine_close_and_currency(close_price, close_ccy)

    return {
        "name": name,
        "url": security_url,
        "source": (lookup or {}).get("source", "") or ("yahoo" if yahoo_symbol else ""),
        "category": (lookup or {}).get("category", ""),
        "txn_close_price": normalize_txn_close_price(close_with_ccy),
        "txn_close_currency": normalize_currency_code(close_ccy),
    }


def resolve_symbol_metadata(symbol, txn_date=None):
    normalized = normalize_symbol(symbol)
    if not normalized:
        return {"name": "", "url": "", "source": "", "category": "", "txn_close_price": ""}
    close_price, close_ccy = yahoo_closing_quote_for_symbol_date(normalized, txn_date) if txn_date else ("", "")
    close_with_ccy = combine_close_and_currency(close_price, close_ccy)
    return {
        "name": yahoo_symbol_name(normalized) or normalized,
        "url": "",
        "source": "yahoo",
        "category": "",
        "txn_close_price": normalize_txn_close_price(close_with_ccy),
        "txn_close_currency": normalize_currency_code(close_ccy),
    }


def resolve_symbol_metadata(symbol, txn_date=None):
    normalized = normalize_symbol(symbol)
    if not normalized:
        return {"name": "", "url": "", "source": "", "category": "", "txn_close_price": ""}
    close_price = yahoo_closing_price_for_symbol_date(normalized, txn_date) if txn_date else ""
    return {
        "name": yahoo_symbol_name(normalized) or normalized,
        "url": "",
        "source": "yahoo",
        "category": "",
        "txn_close_price": normalize_txn_close_price(close_price),
    }


def to_absolute_url(path_or_url):
    value = (path_or_url or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return f"{BASE_DOMAIN}{value}"
    return f"{BASE_DOMAIN}/{value.lstrip('/')}"


def extract_security_url_from_text(payload, isin):
    isin_escaped = re.escape(isin)
    patterns = [
        rf"(/web/Wertpapier/[^\"'<\s?#]*-{isin_escaped})",
        rf"(https?://www\.wealthmanagement\.bnpparibas\.de/web/Wertpapier/[^\"'<\s?#]*-{isin_escaped})",
        rf"(https?:\\/\\/www\.wealthmanagement\.bnpparibas\.de\\/web\\/Wertpapier\\/[^\"'\s?#]*-{isin_escaped})",
        rf"(\/web\/Wertpapier\/[^\"'\s?#]*-{isin_escaped})",
    ]
    for pattern in patterns:
        m = re.search(pattern, payload, flags=re.IGNORECASE)
        if not m:
            continue
        found = m.group(1)
        found = unescape(found).replace("\\/", "/")
        found = found.split("?")[0].split("#")[0]
        return to_absolute_url(found)
    return ""




def strip_tags(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def extract_name_hint_from_text(payload, isin):
    # Try JSON-style objects containing ISIN and a title/name field.
    keys = ("title", "name", "label", "securityName", "instrumentName")
    for key in keys:
        patterns = [
            rf'"{key}"\s*:\s*"([^"\n]{{3,200}})"[^\{{\}}]{{0,400}}"{re.escape(isin)}"',
            rf'"{re.escape(isin)}"[^\{{\}}]{{0,400}}"{key}"\s*:\s*"([^"\n]{{3,200}})"',
        ]
        for pattern in patterns:
            m = re.search(pattern, payload, flags=re.IGNORECASE)
            if not m:
                continue
            name = normalize_name(unescape(m.group(1)).replace('\/', '/'))
            if name and normalize_isin(name) != isin:
                return name

    # Try HTML block around the ISIN and pick nearest meaningful text snippet.
    m_isin = re.search(re.escape(isin), payload, flags=re.IGNORECASE)
    if m_isin:
        start = max(0, m_isin.start() - 1400)
        end = min(len(payload), m_isin.end() + 600)
        snippet = payload[start:end]
        text_before = strip_tags(snippet[: max(0, m_isin.start() - start)])
        candidates = [c.strip() for c in re.split(r"[\n\r]+", text_before) if c.strip()]
        candidates = [c for c in candidates if len(c) > 6]
        stop_words = {"wertpapiere", "suche", "etf", "fonds", "aktie"}
        for c in reversed(candidates[-8:]):
            lowered = c.lower()
            if lowered in stop_words:
                continue
            name = normalize_name(c)
            if name and normalize_isin(name) != isin:
                return name

    return ""

def search_result_pages_for_isin(isin):
    q = quote_plus(isin)
    return [
        f"{BASE_DOMAIN}/web/suche?search={q}",
        f"{BASE_DOMAIN}/web/suche?q={q}",
        f"{BASE_DOMAIN}/web/search?search={q}",
        f"{BASE_DOMAIN}/web/search?q={q}",
        f"{BASE_DOMAIN}/web/suchergebnis?search={q}",
        f"{BASE_DOMAIN}/web/suchergebnis?q={q}",
        f"{BASE_DOMAIN}/web/home?search={q}",
    ]


def search_json_endpoints_for_isin(isin):
    q = quote_plus(isin)
    return [
        f"{BASE_DOMAIN}/web/suche/autocomplete?query={q}",
        f"{BASE_DOMAIN}/web/search/autocomplete?query={q}",
        f"{BASE_DOMAIN}/api/search?query={q}",
        f"{BASE_DOMAIN}/o/search?query={q}",
    ]


def discover_security_url_for_isin(isin):
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Referer": f"{BASE_DOMAIN}/web/home",
    }

    best_name = ""

    for candidate in search_result_pages_for_isin(isin):
        try:
            payload = fetch_text(candidate, headers=headers)
        except Exception:
            continue
        name_hint = extract_name_hint_from_text(payload, isin)
        if name_hint and not best_name:
            best_name = name_hint
        security_url = extract_security_url_from_text(payload, isin)
        if security_url:
            return {"url": security_url, "source": candidate, "name_hint": name_hint or best_name}

    for candidate in search_json_endpoints_for_isin(isin):
        try:
            payload = fetch_text(candidate, headers=headers)
        except Exception:
            continue
        name_hint = extract_name_hint_from_text(payload, isin)
        if name_hint and not best_name:
            best_name = name_hint
        security_url = extract_security_url_from_text(payload, isin)
        if security_url:
            return {"url": security_url, "source": candidate, "name_hint": name_hint or best_name}

    if best_name:
        return {"url": "", "source": "search-text", "name_hint": best_name}

    return None


def extract_security_name_from_page(url):
    html = fetch_text(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Referer": f"{BASE_DOMAIN}/web/home",
        },
    )

    title_match = re.search(
        r'<h1[^>]*class="[^"]*headline-small--fluid[^"]*"[^>]*title="([^"]+)"',
        html,
        flags=re.IGNORECASE,
    )
    if title_match:
        return normalize_name(unescape(title_match.group(1)))

    h1_match = re.search(
        r'<h1[^>]*class="[^"]*headline-small--fluid[^"]*"[^>]*>(.*?)</h1>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if h1_match:
        text = re.sub(r"<[^>]+>", " ", h1_match.group(1))
        text = unescape(re.sub(r"\s+", " ", text))
        return normalize_name(text)

    og_match = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html, flags=re.IGNORECASE)
    if og_match:
        return normalize_name(unescape(og_match.group(1)))

    page_title = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if page_title:
        text = re.sub(r"\s+", " ", page_title.group(1)).strip()
        text = re.sub(r"\s*\|\s*BNP.*$", "", text)
        return normalize_name(unescape(text))

    return ""




def openfigi_name_for_isin(isin):
    # Fallback resolver when BNP page discovery fails.
    try:
        req = Request(
            "https://api.openfigi.com/v3/mapping",
            data=json.dumps([{"idType": "ID_ISIN", "idValue": isin}]).encode("utf-8"),
            headers={
                "User-Agent": UA,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(req, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""

    if not isinstance(payload, list) or not payload:
        return ""
    first = payload[0] if isinstance(payload[0], dict) else {}
    data = first.get("data") or []
    if not data or not isinstance(data[0], dict):
        return ""

    candidate = (
        data[0].get("name")
        or data[0].get("securityDescription")
        or data[0].get("ticker")
        or ""
    )
    candidate = normalize_name(candidate)
    if not candidate:
        return ""
    if normalize_isin(candidate) == isin:
        return ""
    return candidate

def bnp_find_url_and_name_for_isin(isin):
    discovered = discover_security_url_for_isin(isin)
    if not discovered:
        fallback_name = openfigi_name_for_isin(isin)
        if fallback_name:
            return {
                "name": fallback_name,
                "url": "",
                "source": "openfigi",
                "category": "",
            }
        return None

    name_hint = normalize_name(discovered.get("name_hint"))
    if name_hint and normalize_isin(name_hint) != isin:
        return {
            "name": name_hint,
            "url": discovered.get("url", ""),
            "source": discovered.get("source", ""),
            "category": "",
        }

    url = discovered.get("url")
    if not url:
        fallback_name = openfigi_name_for_isin(isin)
        if fallback_name:
            return {
                "name": fallback_name,
                "url": "",
                "source": "openfigi",
                "category": "",
            }
        return None

    try:
        name = extract_security_name_from_page(url)
    except Exception:
        name = ""

    name = normalize_name(name)
    if not name or normalize_isin(name) == isin:
        fallback_name = openfigi_name_for_isin(isin)
        if fallback_name:
            return {
                "name": fallback_name,
                "url": url,
                "source": "openfigi",
                "category": "",
            }
        return None

    parsed = urlparse(url)
    path = parsed.path or ""
    category = ""
    m = re.search(r"/web/Wertpapier/([^/]+)/", path, flags=re.IGNORECASE)
    if m:
        category = m.group(1)

    return {
        "name": name,
        "url": url,
        "source": discovered.get("source", ""),
        "category": category,
    }


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

            user = fetch_json(
                f"{supabase_url}/auth/v1/user",
                {
                    "Authorization": f"Bearer {token}",
                    "apikey": service_key,
                    "Accept": "application/json",
                },
            )
            user_id = user.get("id")
            if not user_id:
                self._send(401, {"status": "error", "message": "Invalid session"})
                return

            supa_headers = {
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Accept": "application/json",
            }

            parsed = urlparse(self.path)
            q = parse_qs(parsed.query)
            isin = normalize_isin((q.get("isin") or [""])[0])
            symbol = normalize_symbol((q.get("symbol") or [""])[0])

            if isin:
                txn_date = (q.get("txn_date") or [""])[0]
                meta = resolve_security_metadata(isin, txn_date=txn_date)
                if not meta.get("name"):
                    self._send(404, {"status": "error", "message": f"No security name found for {isin}"})
                    return
                self._send(200, {"status": "ok", "isin": isin, **meta})
                return

            if symbol:
                txn_date = (q.get("txn_date") or [""])[0]
                meta = resolve_symbol_metadata(symbol, txn_date=txn_date)
                if not meta.get("name"):
                    self._send(404, {"status": "error", "message": f"No security name found for {symbol}"})
                    return
                self._send(200, {"status": "ok", "symbol": symbol, **meta})
                return

            txs = fetch_json(
                f"{supabase_url}/rest/v1/transactions?user_id=eq.{user_id}&select=id,symbol,txn_date,security_name,txn_close_price,price",
                supa_headers,
            )

            canonical_names = {}
            for row in txs:
                row_symbol = normalize_symbol(row.get("symbol"))
                old_name = normalize_name(row.get("security_name"))
                if not row_symbol or not old_name:
                    continue
                row_isin = normalize_isin(row_symbol)
                if row_isin:
                    if normalize_isin(old_name) != row_isin:
                        canonical_names[row_symbol] = old_name
                elif old_name.upper() != row_symbol:
                    canonical_names[row_symbol] = old_name

            pair_cache = {}
            updates = []
            for row in txs:
                row_id = row.get("id")
                row_symbol = normalize_symbol(row.get("symbol"))
                txn_date = str(row.get("txn_date") or "")
                if not row_id or not row_symbol:
                    continue

                row_isin = normalize_isin(row_symbol)
                old_name = normalize_name(row.get("security_name"))
                old_close = normalize_txn_close_price(row.get("txn_close_price"))
                is_placeholder_name = normalize_isin(old_name) == row_isin if row_isin else old_name.upper() == row_symbol
                needs_name = (not old_name) or is_placeholder_name
                old_close_ccy = extract_currency_from_close_text(old_close)
                needs_close = (not old_close) or (txn_date and not old_close_ccy)

                if not needs_name and not needs_close:
                    continue

                key = (row_symbol, txn_date)
                if key not in pair_cache:
                    try:
                        if row_isin:
                            meta = resolve_security_metadata(row_isin, txn_date=txn_date)
                        else:
                            meta = resolve_symbol_metadata(row_symbol, txn_date=txn_date)
                    except Exception:
                        meta = {"name": canonical_names.get(row_symbol, ""), "txn_close_price": "unavailable", "txn_close_currency": ""}

                    if canonical_names.get(row_symbol):
                        meta["name"] = canonical_names[row_symbol]
                    if meta.get("name"):
                        canonical_names[row_symbol] = meta["name"]
                    pair_cache[key] = meta
                meta = pair_cache[key]

                update_row = {"id": row_id, "user_id": user_id}
                if needs_name and meta.get("name"):
                    update_row["security_name"] = meta["name"]
                if needs_close:
                    resolved_close = meta.get("txn_close_price")
                    if not resolved_close:
                        fallback_price = maybe_parse_float(row.get("price"))
                        resolved_close = f"{fallback_price:.4f}" if fallback_price is not None else "unavailable"
                    update_row["txn_close_price"] = resolved_close

                if len(update_row) > 2:
                    updates.append(update_row)

            if updates:
                req = Request(
                    f"{supabase_url}/rest/v1/transactions?on_conflict=id",
                    data=json.dumps(updates).encode("utf-8"),
                    headers={
                        **supa_headers,
                        "Content-Type": "application/json",
                        "Prefer": "resolution=merge-duplicates,return=minimal",
                    },
                    method="POST",
                )
                with urlopen(req, timeout=30):
                    pass

            self._send(200, {
                "status": "ok",
                "updated_rows": len(updates),
                "resolved_symbols": len(pair_cache),
            })
        except Exception as e:
            self._send(500, {"status": "error", "message": str(e)})
