"""A throwaway loopback HTTP server that speaks the profile API.

Used by the integration tests for `HttpProfileRepository`: it exercises the
real `requests` transport, real sockets and real JSON encoding, without
depending on bierre-ca being up.

State lives on the server instance (not the handler class), so two servers in
the same test session never share profiles.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

PROTECTED_IDS = {"generic"}

_GENERIC_PROFILE = {
    "name": "generic",
    "label": "Generic",
    "default_question": "",
    "concepts": [],
    "query_groups": {},
    "off_topic_terms": [],
    "journal_terms": [],
    "term_groups": {},
    "intents": {},
    "buckets": [],
    "extraction_fields": [],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _Store:
    def __init__(self) -> None:
        now = _now_iso()
        self.profiles: dict[str, dict] = {"generic": dict(_GENERIC_PROFILE)}
        self.created_at: dict[str, str] = {"generic": now}
        self.updated_at: dict[str, str] = {"generic": now}


class _ProfileApiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def store(self) -> _Store:
        return self.server.store  # type: ignore[attr-defined]

    # --- routes ---------------------------------------------------------

    def do_GET(self) -> None:
        store = self.store
        if self.path == "/api/profiles":
            meta = [
                {
                    "id": profile_id,
                    "label": payload.get("label", profile_id),
                    "created_at": store.created_at[profile_id],
                    "updated_at": store.updated_at[profile_id],
                    "is_builtin": profile_id in PROTECTED_IDS,
                }
                for profile_id, payload in store.profiles.items()
            ]
            self._send_json({"profiles": [m["id"] for m in meta], "profiles_meta": meta, "default": "generic"})
            return

        profile_id = self._path_profile_id()
        if profile_id is None:
            self._send_json({"error": "not found"}, status=404)
            return
        payload = store.profiles.get(profile_id)
        if payload is None:
            self._send_json({"error": f"Unknown profile {profile_id!r}"}, status=404)
            return
        self._send_json({"id": profile_id, "profile": payload})

    def do_POST(self) -> None:
        if self.path != "/api/profiles":
            self._send_json({"error": "not found"}, status=404)
            return
        store = self.store
        payload = self._read_json()
        label = str(payload.get("name") or payload.get("label") or "").strip()
        if not label:
            self._send_json({"error": "Profile label is required."}, status=400)
            return
        profile_id = label.lower().replace(" ", "-")
        if profile_id in store.profiles:
            self._send_json({"error": f"Profile {profile_id!r} already exists"}, status=409)
            return
        now = _now_iso()
        profile = {**payload, "name": profile_id}
        store.profiles[profile_id] = profile
        store.created_at[profile_id] = now
        store.updated_at[profile_id] = now
        self._send_json({"id": profile_id, "profile": profile}, status=201)

    def do_PUT(self) -> None:
        store = self.store
        profile_id = self._path_profile_id()
        if profile_id is None or profile_id not in store.profiles:
            self._send_json({"error": f"Unknown profile {profile_id!r}"}, status=404)
            return
        payload = self._read_json()
        merged = {**store.profiles[profile_id], **payload, "name": profile_id}
        store.profiles[profile_id] = merged
        store.updated_at[profile_id] = _now_iso()
        self._send_json({"id": profile_id, "profile": merged})

    def do_DELETE(self) -> None:
        store = self.store
        profile_id = self._path_profile_id()
        if profile_id is None or profile_id not in store.profiles:
            self._send_json({"error": f"Unknown profile {profile_id!r}"}, status=404)
            return
        if profile_id in PROTECTED_IDS:
            self._send_json({"error": f"Profile {profile_id!r} is protected and cannot be deleted"}, status=403)
            return
        del store.profiles[profile_id]
        del store.created_at[profile_id]
        del store.updated_at[profile_id]
        self._send_json({"deleted": profile_id})

    # --- plumbing -------------------------------------------------------

    def _path_profile_id(self) -> str | None:
        if not self.path.startswith("/api/profiles/"):
            return None
        return self.path.rsplit("/", 1)[-1]

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) or b"{}"
        payload = json.loads(body)
        return payload if isinstance(payload, dict) else {}

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        """Silence the default stderr access log."""


@contextmanager
def profile_api_server() -> Iterator[str]:
    """Run the mock profile API on an ephemeral loopback port; yield its base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProfileApiHandler)
    server.store = _Store()  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, name="mock-profile-api", daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
