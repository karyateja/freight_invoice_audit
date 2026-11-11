"""HTTP server: static single-page app + JSON API. Python standard library only."""
from __future__ import annotations

import json
import mimetypes
import re
import sys
import traceback
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from . import api, jobs, quote
from .datasets import BadRequest, Busy, Dataset, NotFound, list_datasets

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 64 * 1024
ID = r"([A-Za-z0-9_.-]+)"

# (method, pattern, handler(match, query, body) -> value)
ROUTES = [
    ("GET", r"/api/meta", lambda m, q, b: api.meta()),
    ("GET", r"/api/datasets", lambda m, q, b: list_datasets()),
    ("GET", rf"/api/d/{ID}/overview", lambda m, q, b: api.overview(Dataset(m[1]))),
    ("GET", rf"/api/d/{ID}/filters", lambda m, q, b: api.filters(Dataset(m[1]))),
    ("GET", rf"/api/d/{ID}/validation", lambda m, q, b: api.validation(Dataset(m[1]))),
    ("GET", rf"/api/d/{ID}/exceptions", lambda m, q, b: api.exceptions(Dataset(m[1]), q)),
    ("GET", rf"/api/d/{ID}/exceptions/{ID}", lambda m, q, b: api.exception_detail(Dataset(m[1]), m[2])),
    ("GET", rf"/api/d/{ID}/invoices", lambda m, q, b: api.invoices(Dataset(m[1]), q)),
    ("GET", rf"/api/d/{ID}/invoices/{ID}", lambda m, q, b: api.invoice_detail(Dataset(m[1]), m[2])),
    ("GET", rf"/api/d/{ID}/shipments/{ID}", lambda m, q, b: api.shipment_detail(Dataset(m[1]), m[2])),
    ("GET", rf"/api/d/{ID}/shipments/{ID}/quote-input",
     lambda m, q, b: quote.prefill_from_shipment(Dataset(m[1]), m[2])),
    ("GET", rf"/api/d/{ID}/carriers/{ID}", lambda m, q, b: api.carrier_detail(Dataset(m[1]), m[2])),
    ("GET", rf"/api/d/{ID}/rate-lines", lambda m, q, b: api.rate_lines(Dataset(m[1]), q)),
    ("GET", rf"/api/d/{ID}/rate-options", lambda m, q, b: api.rate_options(Dataset(m[1]), q)),
    ("GET", rf"/api/d/{ID}/schema", lambda m, q, b: api.schema_info(Dataset(m[1]))),
    ("POST", rf"/api/d/{ID}/quote", lambda m, q, b: quote.quote(Dataset(m[1]), b)),
    ("POST", rf"/api/d/{ID}/sql", lambda m, q, b: api.run_sql(Dataset(m[1]), b.get("sql", ""))),
    ("GET", r"/api/jobs", lambda m, q, b: jobs.all_jobs()),
    ("POST", r"/api/jobs", lambda m, q, b: jobs.start(b)),
    ("GET", r"/api/jobs/(\d+)", lambda m, q, b: jobs.get(int(m[1]), int(q.get("from", 0) or 0))),
    ("POST", r"/api/jobs/(\d+)/cancel", lambda m, q, b: jobs.cancel(int(m[1]))),
]
COMPILED = [(meth, re.compile(f"^{pat}$"), fn) for meth, pat, fn in ROUTES]


def _default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, bytes):
        return o.hex()
    return str(o)


class Handler(BaseHTTPRequestHandler):
    server_version = "FreightAuditWeb/1.0"
    quiet = False

    def log_message(self, fmt, *args):
        if not self.quiet:
            sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    # ------------------------------------------------------------------ helpers
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj):
        self._send(status, json.dumps(obj, default=_default).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, msg: str):
        self._json(status, {"error": msg})

    # ------------------------------------------------------------------ dispatch
    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str):
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        if path.startswith("/api/"):
            return self._api(method, path, dict(parse_qsl(parts.query)))
        if method != "GET":
            return self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
        m = re.match(rf"^/files/{ID}/(.+)$", path)
        if m:
            return self._download(m[1], m[2])
        return self._static(path)

    def _api(self, method: str, path: str, query: dict):
        body = {}
        if method == "POST":
            if self.headers.get("Origin") and not self._same_origin():
                return self._error(HTTPStatus.FORBIDDEN, "cross-origin request refused")
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._error(HTTPStatus.BAD_REQUEST, "body must be a JSON object")
        allowed = []
        for meth, rx, fn in COMPILED:
            m = rx.match(path)
            if not m:
                continue
            if meth != method:
                allowed.append(meth)
                continue
            try:
                result = fn(m, query, body)
            except NotFound as exc:
                return self._error(HTTPStatus.NOT_FOUND, f"not found: {exc}")
            except BadRequest as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Busy as exc:
                return self._error(HTTPStatus.CONFLICT, str(exc))
            except Exception as exc:  # never leak a half-written response
                traceback.print_exc()
                return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(exc).__name__}: {exc}")
            if result is None:
                return self._error(HTTPStatus.NOT_FOUND, "not found")
            return self._json(HTTPStatus.CREATED if method == "POST" and path == "/api/jobs" else HTTPStatus.OK,
                              result)
        if allowed:
            return self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
        return self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def _same_origin(self) -> bool:
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin", "")
        return origin in (f"http://{host}", f"https://{host}")

    def _download(self, ds_name: str, rel: str):
        try:
            p = Dataset(ds_name).file_path(rel)
        except (NotFound, Busy) as exc:
            return self._error(HTTPStatus.NOT_FOUND, str(exc))
        ctype = {".md": "text/markdown; charset=utf-8", ".csv": "text/csv; charset=utf-8",
                 ".json": "application/json; charset=utf-8", ".sql": "text/plain; charset=utf-8"}.get(
            p.suffix, "application/octet-stream")
        self._send(HTTPStatus.OK, p.read_bytes(), ctype,
                   {"Content-Disposition": f'inline; filename="{p.name}"'})

    def _static(self, path: str):
        rel = path.lstrip("/") or "index.html"
        p = (STATIC / rel).resolve()
        if STATIC.resolve() not in p.parents or not p.is_file():
            p = STATIC / "index.html"   # SPA: unknown paths fall back to the app shell
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(HTTPStatus.OK, p.read_bytes(), ctype)


def make_server(host: str = "127.0.0.1", port: int = 8000, quiet: bool = False) -> ThreadingHTTPServer:
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    handler = type("H", (Handler,), {"quiet": quiet})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv
