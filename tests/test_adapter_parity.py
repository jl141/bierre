from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli
from core.config import Settings
from core.contracts.run_search import RunSearchResponse, CONTRACT_VERSION
from webapp import server as web_server


def _canonical_response() -> RunSearchResponse:
    return RunSearchResponse(
        contract_version=CONTRACT_VERSION,
        request_id="req_1",
        run_id="run_1",
        timestamp="2026-08-06T00:00:00+00:00",
        mode="offline",
        profile_id="generic",
        question="q",
        queries=["q"],
        apis_used=["OfflineMock"],
        scoring_summary={
            "strategy": "hybrid",
            "selection_enabled": True,
            "selection_top_n": 10,
            "selection_min_relevance": 30.0,
        },
        counts={"found": 1, "selected": 1},
        papers=[{"title": "T", "selected": True, "relevance_percent": 90.0, "bucket": "Core"}],
        evidence=[{"paper_id": "P0001"}],
        errors=[],
    )


class _FakeSearchService:
    def __init__(self, _base_settings=None, **_kwargs) -> None:
        pass

    def run(self, _request, progress=None) -> RunSearchResponse:
        if progress:
            progress(1, 1, "done")
        return _canonical_response()


def test_cli_and_web_emit_same_canonical_payload() -> None:
    expected_payload = _canonical_response().to_dict()

    original_cli_service = cli.SearchService
    cli.SearchService = _FakeSearchService
    try:
        with TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "out.json"
            exit_code = cli.main(["-q", "q", "--offline", "--quiet", "--json", str(json_path)])
            assert exit_code == 0
            cli_payload = json.loads(json_path.read_text(encoding="utf-8"))
    finally:
        cli.SearchService = original_cli_service

    assert cli_payload == expected_payload

    app = web_server.create_app(Settings.from_dict({"profile": "generic"}))
    app.state.search_service = _FakeSearchService()

    with TestClient(app) as client:
        response = client.post(
            "/api/run",
            json={"question": "q", "offline": True, "profile_id": "generic"},
        )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.strip()]
    result_events = [json.loads(line) for line in lines if json.loads(line).get("type") == "result"]
    assert len(result_events) == 1
    web_payload = result_events[0]["result"]
    assert web_payload == expected_payload


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All adapter parity tests passed.")
