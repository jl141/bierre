"""A throwaway loopback stand-in for `bierre-ca`'s `/accounts` surface.

Used by the proxy tests: the point is to exercise the real transport, so the
things a proxy gets wrong — dropped credentials, folded `Set-Cookie` headers,
rewritten status codes — actually show up. Most paths echo the request back so a
test can assert on what arrived; the few that do something specific are the ones
whose response headers a proxy has to relay.

Received requests are recorded on the server instance, never on the handler
class, so two servers in one session never share state.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator
from urllib.parse import urlsplit

REFRESH_COOKIE = (
    "bierre_refresh=opaque-session; HttpOnly; Secure; SameSite=Lax; "
    "Path=/accounts/api/auth; Expires=Wed, 21 Oct 2026 07:28:00 GMT"
)
CSRF_COOKIE = "bierre_csrf=double-submit; Secure; SameSite=Lax; Path=/; Expires=Wed, 21 Oct 2026 07:28:00 GMT"

ECHOED_REQUEST_HEADERS = (
    "authorization",
    "cookie",
    "x-csrf-token",
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "content-type",
)


class _AccountsHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def _handle(self) -> None:
        path, _, query = urlsplit(self.path).geturl().partition("?")
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        received = {
            "method": self.command,
            "path": path,
            "query": query,
            "headers": {name: self.headers.get(name) for name in ECHOED_REQUEST_HEADERS},
            "body": body.decode("utf-8"),
        }
        self.server.received.append(received)  # type: ignore[attr-defined]

        if path == "/accounts/api/auth/login":
            self._send_json(received, cookies=[REFRESH_COOKIE, CSRF_COOKIE])
        elif path == "/accounts/api/auth/refresh":
            self._send_json({"error": "Too many requests."}, status=429, headers={"Retry-After": "30"})
        elif path == "/accounts/api/auth/me" and not self.headers.get("Authorization"):
            self._send_json({"error": "Sign in first."}, status=401)
        elif path == "/accounts/api/auth/logout":
            self._send_empty(204)
        else:
            self._send_json(received)

    def _send_json(
        self,
        payload: dict,
        status: int = 200,
        cookies: list[str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args) -> None:
        """Silence the default stderr access log."""


@contextmanager
def accounts_api_server() -> Iterator[tuple[str, list[dict]]]:
    """Run the fake account service; yield its base URL and the requests it saw."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AccountsHandler)
    server.received = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, name="fake-accounts-api", daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}", server.received  # type: ignore[attr-defined]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
