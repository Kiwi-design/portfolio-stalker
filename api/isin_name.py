from http.server import BaseHTTPRequestHandler
import json
import os
import re
from urllib.parse import urlencode, urlparse, parse_qs, quote_plus
from urllib.request import Request, urlopen

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
ISIN_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{10}\b")
INVALID_NAME_VALUES = {"", "null", "none", "n/a", "na", "undefined", "-"}


def fetch_json(url, headers=None, timeout=25):
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url, headers=None, timeout=25):
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def walk_for_records(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk_for_records(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_for_records(item)


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


def build_ajax_url(template, page):
    if "{page}" in template:
        return template.format(page=page)
    parsed = urlparse(template)
    q = parse_qs(parsed.query)
    q["page"] = [str(page)]
    new_query = urlencode({k: v[0] for k, v in q.items()})
    return parsed._replace(query=new_query).geturl()


def bnp_find_url_and_name_for_isin(isin):
    templates = [
        x.strip() for x in os.environ.get("BNP_WM_AJAX_HISTORY_URLS", "").split(",") if x.strip()
    ]
    if not templates:
        templates = [
            "https://wealthmanagement.bnpparibas/en/search/results/_jcr_content/ajaxhistory.json?page={page}",
            "https://wealthmanagement.bnpparibas/en/search-results/_jcr_content/ajaxhistory.json?page={page}",
        ]

    page_limit = int(os.environ.get("BNP_WM_PAGE_LIMIT", "120"))
    headers = {"User-Agent": UA, "Accept": "application/json"}

    for template in templates:
        for page in range(1, page_limit + 1):
            try:
                payload = fetch_json(build_ajax_url(template, page), headers=headers)
            except Exception:
                break

            matched = None
            for rec in walk_for_records(payload):
            records = list(walk_for_records(payload))
            matched = None
            for rec in records:
                rec_isin = normalize_isin(read_str(rec, ["isin", "symbol", "code", "identifier"]))
                if not rec_isin:
                    blob = " ".join(
                        str(rec.get(key, ""))
                        for key in ("url", "href", "path", "title", "name", "description")
                    )
                    rec_isin = normalize_isin(blob)
                if rec_isin == isin:
                    matched = rec
                    break

            if not matched:
                continue

            url = read_str(matched, ["url", "href", "path", "link"])
            if url and url.startswith("/"):
                url = f"https://wealthmanagement.bnpparibas{url}"

            name = normalize_name(read_str(matched, ["title", "name", "label", "securityName"]))
            if not name and url:
                try:
                    html = fetch_text(url, headers={"User-Agent": UA, "Accept": "text/html"})
                    m = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
                    if m:
                        title = re.sub(r"\s+", " ", m.group(1)).strip()
                        title = re.sub(r"\s*\|\s*BNP.*$", "", title)
                        name = normalize_name(title)
                except Exception:
                    pass

            if name:
                return {"name": name, "url": url, "page": page, "source": build_ajax_url(template, page)}

            if matched:
                url = read_str(matched, ["url", "href", "path", "link"])
                if url and url.startswith("/"):
                    url = f"https://wealthmanagement.bnpparibas{url}"
                name = read_str(matched, ["title", "name", "label", "securityName"])
                if not name and url:
                    try:
                        html = fetch_text(url, headers={"User-Agent": UA, "Accept": "text/html"})
                        m = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
                        if m:
                            name = re.sub(r"\s+", " ", m.group(1)).strip()
                            name = re.sub(r"\s*\|\s*BNP.*$", "", name)
                    except Exception:
                        pass
                if name:
                    return {"name": name, "url": url, "page": page, "source": build_ajax_url(template, page)}
                return {"name": "", "url": url, "page": page, "source": build_ajax_url(template, page)}

    # Last fallback: directly try an ISIN details URL template (if configured)
    direct_template = os.environ.get("BNP_WM_ISIN_URL_TEMPLATE", "").strip()
    if direct_template:
        url = direct_template.replace("{isin}", quote_plus(isin))
        try:
            html = fetch_text(url, headers={"User-Agent": UA, "Accept": "text/html"})
            m = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()
                title = re.sub(r"\s*\|\s*BNP.*$", "", title)
                title = normalize_name(title)
                if title:
                    return {"name": title, "url": url, "source": "direct-template"}
                return {"name": title, "url": url, "source": "direct-template"}
        except Exception:
            pass

    return None


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
                if lookup and lookup.get("name"):
                    self._send(200, {"status": "ok", "isin": isin, **lookup})
                    return
                # Never return NULL-like name to frontend; fallback to ISIN.
                self._send(200, {
                    "status": "ok",
                    "isin": isin,
                    "name": isin,
                    "fallback": True,
                    "message": f"No BNP Wealth Management name found for {isin}; using ISIN as fallback",
                })
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
                resolved[symbol] = normalize_name((lookup or {}).get("name")) or symbol
                if not lookup or not lookup.get("name"):
                    continue
                resolved[symbol] = lookup.get("name")

            for row in txs:
                row_isin = normalize_isin(row.get("symbol"))
                if not row_isin:
                    continue
                new_name = resolved.get(row_isin) or row_isin
                old_name = normalize_name(row.get("security_name"))
                new_name = resolved.get(row_isin)
                if not new_name:
                    continue
                old_name = (row.get("security_name") or "").strip()
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
