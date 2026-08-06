#!/usr/bin/env python3
"""Local web UI for the bierre workflow.

    python webapp/server.py
    open http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import (  # noqa: E402
    ProfileService,
    RunSearchRequest,
    SearchService,
    Settings,
    build_profile_repository,
)
from core.repositories.profile_repository import (  # noqa: E402
    DomainProfile,
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileValidationError,
    ProtectedProfileError,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
_CONTENT_TYPES = {".html": "text/html", ".css": "text/css", ".js": "application/javascript"}


def _settings_to_dict(s: Settings) -> dict:
    return {
        "contact_email": s.contact_email,
        "use_unpaywall": s.use_unpaywall,
        "api_keys": dict(s.api_keys),
        "search": {
            "max_results_per_query": s.search.max_results_per_query,
            "max_queries_per_run": s.search.max_queries_per_run,
            "concurrent_workers": s.search.concurrent_workers,
            "timeout_seconds": s.search.timeout_seconds,
            "enabled_sources": list(s.search.enabled_sources),
            "semantic_scholar_max_queries_without_key": s.search.semantic_scholar_max_queries_without_key,
            "source_http_overrides": dict(s.search.source_http_overrides),
        },
        "selection": {
            "enabled": s.selection.enabled,
            "top_n": s.selection.top_n,
            "min_relevance": s.selection.min_relevance,
        },
        "profile_repository": {
            "mode": s.profile_repository.mode,
            "base_url": s.profile_repository.base_url,
            "timeout_seconds": s.profile_repository.timeout_seconds,
            "max_attempts": s.profile_repository.max_attempts,
            "backoff_base_seconds": s.profile_repository.backoff_base_seconds,
            "backoff_max_seconds": s.profile_repository.backoff_max_seconds,
        },
    }


def _profile_loader_from_service(profile_service: ProfileService):
    def _loader(profile_id: str) -> DomainProfile:
        payload = profile_service.get_profile(profile_id)
        return DomainProfile.from_dict({**payload, "name": profile_id})

    return _loader


class Handler(BaseHTTPRequestHandler):
    # Read-only config shared by all requests; set in main().
    settings: Settings = Settings()
    search_service: SearchService = SearchService(base_settings=settings)
    profile_service: ProfileService = ProfileService()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_static("index.html")
        elif path in ("/styles.css", "/app.js"):
            self._send_static(path.lstrip("/"))
        elif path == "/api/profiles":
            self._handle_list_profiles()
        elif path.startswith("/api/profiles/"):
            profile_id = self._profile_id_from_path(path)
            if profile_id is None:
                self.send_error(404)
                return
            self._handle_get_profile(profile_id)
        elif path == "/api/settings":
            self._send_json(_settings_to_dict(self.settings))
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/run":
            self._handle_run()
            return
        if path == "/api/profiles":
            self._handle_create_profile()
            return
        if path == "/bierre-ca/api/generate":
            self._handle_profile_generate()
            return
        self.send_error(404)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/profiles/"):
            self.send_error(404)
            return
        profile_id = self._profile_id_from_path(path)
        if profile_id is None:
            self.send_error(404)
            return
        self._handle_update_profile(profile_id)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/profiles/"):
            self.send_error(404)
            return
        profile_id = self._profile_id_from_path(path)
        if profile_id is None:
            self.send_error(404)
            return
        self._handle_delete_profile(profile_id)

    def _handle_run(self) -> None:
        stream_started = False
        try:
            payload = self._read_json()
            settings_overrides = payload.get("settings_overrides")
            if settings_overrides is None:
                settings_overrides = payload.get("settings") or {}
            profile_id = str(payload.get("profile_id") or payload.get("profile") or self.settings.profile).strip()
            question = str(payload.get("question") or "").strip()
            if not question:
                # Preserve prior UX where empty question falls back to profile default.
                question = str(self.profile_service.get_profile(profile_id).get("default_question") or "").strip()
            request = RunSearchRequest(
                question=question,
                profile_id=profile_id,
                offline=bool(payload.get("offline")),
                settings_overrides=dict(settings_overrides or {}),
                requested_outputs=list(payload.get("requested_outputs") or []),
                request_id=str(payload.get("request_id") or "").strip(),
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            stream_started = True

            def emit(event: dict) -> None:
                self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()

            def on_progress(step: int, total: int, label: str) -> None:
                emit({"type": "progress", "step": step, "total": total, "label": label})

            result = self.search_service.run(request, progress=on_progress)
            emit({"type": "result", "result": result.to_dict()})
        except BrokenPipeError:
            # Client disconnected mid-run; no further write possible.
            return
        except ProfileValidationError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:  # surface failures to the UI rather than 500-ing silently
            with suppress(BrokenPipeError):
                # If stream headers were already sent, ship an event; else return normal JSON error.
                if stream_started:
                    self.wfile.write((json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
                    return
            self._send_json({"error": str(exc)}, status=500)

    def _handle_list_profiles(self) -> None:
        profiles = [item.to_dict() for item in self.profile_service.list_profiles()]
        self._send_json(
            {
                "profiles": [item["id"] for item in profiles],
                "profiles_meta": profiles,
                "default": self.settings.profile,
            }
        )

    def _handle_get_profile(self, profile_id: str) -> None:
        try:
            profile = self.profile_service.get_profile(profile_id)
            self._send_json({"id": profile_id, "profile": profile})
        except ProfileNotFoundError as exc:
            self._send_json({"error": str(exc)}, status=404)
        except ProfileValidationError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_create_profile(self) -> None:
        try:
            payload = self._read_json()
            created = self.profile_service.create_profile(payload)
            self._send_json(created, status=201)
        except ProfileValidationError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except ProfileConflictError as exc:
            self._send_json({"error": str(exc)}, status=409)

    def _handle_update_profile(self, profile_id: str) -> None:
        try:
            payload = self._read_json()
            updated = self.profile_service.update_profile(profile_id, payload)
            self._send_json(updated)
        except ProfileNotFoundError as exc:
            self._send_json({"error": str(exc)}, status=404)
        except ProfileValidationError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _handle_delete_profile(self, profile_id: str) -> None:
        try:
            self.profile_service.delete_profile(profile_id)
            self._send_json({"deleted": profile_id})
        except ProfileNotFoundError as exc:
            self._send_json({"error": str(exc)}, status=404)
        except ProfileValidationError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except ProtectedProfileError as exc:
            self._send_json({"error": str(exc)}, status=403)

    def _handle_profile_generate(self) -> None:
        stream_started = False
        try:
            payload = self._read_json()
            research_description = str(payload.get("research_description") or "").strip()
            label_hint = str(payload.get("label_hint") or "").strip()
            if not research_description:
                raise ProfileValidationError("research_description is required.")

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            stream_started = True

            def emit(event: dict) -> None:
                self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()

            emit({"type": "progress", "step": 1, "total": 3, "label": "Preparing prompt"})

            request_payload = {"research_description": research_description}
            if label_hint:
                request_payload["label_hint"] = label_hint

            base_url = os.environ.get("BIERRE_CA_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
            target_url = f"{base_url}/api/generate"
            req_headers = {"Content-Type": "application/json"}
            bierre_ca_api_key = (os.environ.get("BIERRE_CA_API_KEY") or "").strip()
            if bierre_ca_api_key:
                req_headers["X-API-Key"] = bierre_ca_api_key

            emit({"type": "progress", "step": 2, "total": 3, "label": "Generating profile"})

            request = Request(
                target_url,
                data=json.dumps(request_payload).encode("utf-8"),
                headers=req_headers,
                method="POST",
            )
            with urlopen(request, timeout=75) as response:
                data = json.loads(response.read().decode("utf-8") or "{}")

            emit({"type": "progress", "step": 3, "total": 3, "label": "Applying draft"})
            emit({"type": "result", "result": data})
        except BrokenPipeError:
            return
        except HTTPError as exc:
            detail = "Profile generation failed"
            try:
                err_payload = json.loads((exc.read() or b"{}").decode("utf-8"))
                detail = str(err_payload.get("detail") or err_payload.get("error") or detail)
            except Exception:
                detail = str(exc) or detail

            with suppress(BrokenPipeError):
                if stream_started:
                    self.wfile.write((json.dumps({"type": "error", "error": detail}, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
                    return
            self._send_json({"error": detail}, status=502)
        except URLError as exc:
            message = f"Cannot reach bierre-ca service: {exc.reason}"
            with suppress(BrokenPipeError):
                if stream_started:
                    self.wfile.write((json.dumps({"type": "error", "error": message}, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
                    return
            self._send_json({"error": message}, status=502)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            with suppress(BrokenPipeError):
                if stream_started:
                    self.wfile.write((json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
                    return
            self._send_json({"error": str(exc)}, status=500)

    # --- helpers ---

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(payload, dict):
            raise ProfileValidationError("Request body must be a JSON object.")
        return payload

    def _profile_id_from_path(self, path: str) -> str | None:
        prefix = "/api/profiles/"
        if not path.startswith(prefix):
            return None
        tail = unquote(path[len(prefix) :]).strip()
        if not tail or "/" in tail:
            return None
        return tail

    def _send_static(self, name: str) -> None:
        path = STATIC_DIR / name
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self._respond(body, _CONTENT_TYPES.get(path.suffix, "application/octet-stream"))

    def _send_json(self, data: dict, status: int = 200) -> None:
        self._respond(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json", status)

    def _respond(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:  # keep the console quiet
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local bierre web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", type=Path, help="Path to a settings YAML file.")
    args = parser.parse_args(argv)

    Handler.settings = Settings.load(args.config)
    repository = build_profile_repository(Handler.settings)
    Handler.profile_service = ProfileService(repository=repository)
    profile_loader = _profile_loader_from_service(Handler.profile_service)
    Handler.search_service = SearchService(base_settings=Handler.settings, profile_loader=profile_loader)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"bierre web UI on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
