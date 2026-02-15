from http.server import BaseHTTPRequestHandler
import json
import os
import re
from html import unescape
from urllib.parse import quote_plus, parse_qs, urlparse
from urllib.request import Request, urlopen

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
ISIN_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{10}\b")
INVALID_NAME_VALUES = {"", "null", "none", "n/a", "na", "undefined", "-"}
BASE_DOMAIN = "https://www.wealthmanagement.bnpparibas.de"


def fetch_text(url, headers=None, timeout=25):
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url, headers=None, timeout=25):
    return json.loads(fetch_text(url, headers=headers, timeout=timeout))


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


def normalize_name(value):
    if not value:
        return ""
    name = re.sub(r"\s+", " ", str(value)).strip()
    if name.lower() in INVALID_NAME_VALUES:
        return ""
    return name


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

    for candidate in search_result_pages_for_isin(isin):
        try:
            payload = fetch_text(candidate, headers=headers)
        except Exception:
            continue
        security_url = extract_security_url_from_text(payload, isin)
        if security_url:
            return {"url": security_url, "source": candidate}

    for candidate in search_json_endpoints_for_isin(isin):
        try:
            payload = fetch_text(candidate, headers=headers)
        except Exception:
            continue
        security_url = extract_security_url_from_text(payload, isin)
        if security_url:
            return {"url": security_url, "source": candidate}

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


def bnp_find_url_and_name_for_isin(isin):
    discovered = discover_security_url_for_isin(isin)
    if not discovered:
        return None

    url = discovered.get("url")
    if not url:
        return None

    try:
        name = extract_security_name_from_page(url)
    except Exception:
        name = ""

    name = normalize_name(name)
    if not name:
        return None

    if normalize_isin(name) == isin:
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

            if isin:
                lookup = bnp_find_url_and_name_for_isin(isin)
                if not lookup or not lookup.get("name"):
                    self._send(404, {"status": "error", "message": f"No BNP Wealth Management security name found for {isin}"})
                    return
                self._send(200, {"status": "ok", "isin": isin, **lookup})
                return

            txs = fetch_json(
                f"{supabase_url}/rest/v1/transactions?user_id=eq.{user_id}&select=id,symbol,security_name",
                supa_headers,
            )
            symbols = sorted({normalize_isin(t.get("symbol")) for t in txs if normalize_isin(t.get("symbol"))})
            resolved = {}
            updates = []
            for symbol in symbols:
                lookup = bnp_find_url_and_name_for_isin(symbol)
                resolved_name = normalize_name((lookup or {}).get("name"))
                if resolved_name:
                    resolved[symbol] = resolved_name

            for row in txs:
                row_isin = normalize_isin(row.get("symbol"))
                if not row_isin:
                    continue
                new_name = resolved.get(row_isin)
                if not new_name:
                    continue
                old_name = normalize_name(row.get("security_name"))
                if old_name == new_name:
                    continue
                updates.append({"id": row.get("id"), "user_id": user_id, "security_name": new_name})

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
                "resolved_symbols": resolved,
            })
        except Exception as e:
            self._send(500, {"status": "error", "message": str(e)})
