"""CLI and web must emit byte-identical canonical payloads.

This is the regression test for the whole point of the contract layer: two
adapters, one shape. Both are fed the same stubbed service, so any difference
is the adapter's fault.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

import cli
from core.config import Settings
from tests.e2e.conftest import FakeSearchService
from webapp import server as web_server


def _cli_payload(monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(cli, "SearchService", FakeSearchService)
    with TemporaryDirectory() as tmp:
        json_path = Path(tmp) / "out.json"
        assert cli.main(["-q", "q", "--offline", "--quiet", "--json", str(json_path)]) == 0
        return json.loads(json_path.read_text(encoding="utf-8"))


def _web_payload() -> dict:
    app = web_server.create_app(Settings.from_dict({"profile": "generic"}))
    app.state.search_service = FakeSearchService()

    with TestClient(app) as client:
        response = client.post(
            "/api/run", json={"question": "q", "offline": True, "profile_id": "generic"}
        )

    assert response.status_code == 200
    results = [
        json.loads(line)
        for line in response.text.splitlines()
        if line.strip() and json.loads(line).get("type") == "result"
    ]
    assert len(results) == 1
    return results[0]["result"]


def test_cli_and_web_emit_the_same_canonical_payload(
    monkeypatch: pytest.MonkeyPatch, canonical_payload: dict
) -> None:
    assert _cli_payload(monkeypatch) == canonical_payload
    assert _web_payload() == canonical_payload
