#!/usr/bin/env python3
"""Local web UI for the bierre workflow.

A thin adapter over ``core.run_pipeline``: it serves static files and a small
JSON API. Unlike the original, there is **no module-level run state** — each
request runs the pipeline and returns the result directly in its response, so
the browser owns the view state. This is the seam a React SPA / hosted API would
later plug into (Phase 2).

    python webapp/server.py
    open http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Settings, available_profiles, load_profile, run_pipeline  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
_CONTENT_TYPES = {".html": "text/html", ".css": "text/css", ".js": "application/javascript"}


class Handler(BaseHTTPRequestHandler):
    # Read-only config shared by all requests; set in main().
    settings: Settings = Settings()

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send_static("index.html")
        elif self.path in ("/styles.css", "/app.js"):
            self._send_static(self.path.lstrip("/"))
        elif self.path == "/api/profiles":
            self._send_json({"profiles": available_profiles(), "default": self.settings.profile})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/api/run":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = run_pipeline(
                question=str(payload.get("question", "")),
                settings=self.settings,
                profile=load_profile(payload.get("profile") or self.settings.profile),
                offline=bool(payload.get("offline")),
            )
            self._send_json(result.to_dict())
        except Exception as exc:  # surface failures to the UI rather than 500-ing silently
            self._send_json({"error": str(exc)}, status=500)

    # --- helpers ---

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
