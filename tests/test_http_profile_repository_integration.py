from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.repositories.http_profile_repository import HttpProfileRepository
from core.repositories.profile_repository import ProfileNotFoundError


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _MockProfileApiHandler(BaseHTTPRequestHandler):
    _store: dict[str, dict] = {
        "generic": {
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
    }
    _created_at: dict[str, str] = {"generic": _now_iso()}
    _updated_at: dict[str, str] = {"generic": _now_iso()}

    def do_GET(self) -> None:
        if self.path == "/api/profiles":
            meta = []
            for profile_id, payload in self._store.items():
                meta.append(
                    {
                        "id": profile_id,
                        "label": payload.get("label", profile_id),
                        "created_at": self._created_at[profile_id],
                        "updated_at": self._updated_at[profile_id],
                        "is_builtin": profile_id == "generic",
                    }
                )
            self._send_json({"profiles": [m["id"] for m in meta], "profiles_meta": meta, "default": "generic"})
            return

        if self.path.startswith("/api/profiles/"):
            profile_id = self.path.rsplit("/", 1)[-1]
            payload = self._store.get(profile_id)
            if payload is None:
                self._send_json({"error": f"Unknown profile {profile_id!r}"}, status=404)
                return
            self._send_json({"id": profile_id, "profile": payload})
            return

        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path != "/api/profiles":
            self._send_json({"error": "not found"}, status=404)
            return
        payload = self._read_json()
        profile_id = str(payload.get("name") or payload.get("label", "profile")).strip().lower().replace(" ", "-")
        if profile_id in self._store:
            self._send_json({"error": f"Profile {profile_id!r} already exists"}, status=409)
            return
        now = _now_iso()
        profile = {**payload, "name": profile_id}
        self._store[profile_id] = profile
        self._created_at[profile_id] = now
        self._updated_at[profile_id] = now
        self._send_json({"id": profile_id, "profile": profile}, status=201)

    def do_PUT(self) -> None:
        if not self.path.startswith("/api/profiles/"):
            self._send_json({"error": "not found"}, status=404)
            return
        profile_id = self.path.rsplit("/", 1)[-1]
        if profile_id not in self._store:
            self._send_json({"error": f"Unknown profile {profile_id!r}"}, status=404)
            return
        payload = self._read_json()
        merged = {**self._store[profile_id], **payload, "name": profile_id}
        self._store[profile_id] = merged
        self._updated_at[profile_id] = _now_iso()
        self._send_json({"id": profile_id, "profile": merged})

    def do_DELETE(self) -> None:
        if not self.path.startswith("/api/profiles/"):
            self._send_json({"error": "not found"}, status=404)
            return
        profile_id = self.path.rsplit("/", 1)[-1]
        if profile_id not in self._store:
            self._send_json({"error": f"Unknown profile {profile_id!r}"}, status=404)
            return
        if profile_id == "generic":
            self._send_json({"error": "Profile 'generic' is protected and cannot be deleted"}, status=403)
            return
        del self._store[profile_id]
        del self._created_at[profile_id]
        del self._updated_at[profile_id]
        self._send_json({"deleted": profile_id})

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
        return


def _run_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockProfileApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_http_profile_repository_full_crud_flow() -> None:
    server, base_url = _run_server()
    try:
        repo = HttpProfileRepository(base_url=base_url, timeout_seconds=3)

        created = repo.create_profile({"label": "Hydrogel Search", "default_question": "q1"})
        profile_id = created["id"]
        assert profile_id == "hydrogel-search"

        listed = repo.list_profiles()
        assert any(item.profile_id == profile_id for item in listed)

        loaded = repo.get_profile(profile_id)
        assert loaded["label"] == "Hydrogel Search"

        updated = repo.update_profile(profile_id, {"default_question": "q2"})
        assert updated["profile"]["default_question"] == "q2"

        repo.delete_profile(profile_id)

        try:
            repo.get_profile(profile_id)
        except ProfileNotFoundError:
            pass
        else:
            raise AssertionError("Expected ProfileNotFoundError after delete")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All HTTP profile repository integration tests passed.")
