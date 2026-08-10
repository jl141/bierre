"""End-to-end `POST /api/run`: NDJSON progress stream plus a result event."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from core.config import Settings
from core.repositories.yaml_profile_repository import YamlProfileRepository
from core.services.profile_service import ProfileService
from core.services.search_service import SearchService
from tests.factories import profile_payload


@pytest.fixture
def run_client(profiles_dir, monkeypatch) -> TestClient:
    """The real app, real pipeline, temp profiles — everything but the network."""
    from webapp import server

    YamlProfileRepository(profiles_dir).create_profile(
        profile_payload(name="generic", label="Generic", default_question="fallback question")
    )
    settings = Settings.from_dict({"profile": "generic", "search": {"enabled_sources": []}})
    app = server.create_app(settings)
    profile_service = ProfileService(repository=YamlProfileRepository(profiles_dir))
    app.state.profile_service = profile_service
    app.state.search_service = SearchService(
        base_settings=settings, profile_loader=server._profile_loader(profile_service)
    )
    with TestClient(app) as client:
        yield client


def _events(response) -> list[dict]:
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_an_offline_run_streams_progress_then_exactly_one_result(run_client: TestClient) -> None:
    events = _events(
        run_client.post("/api/run", json={"question": "coating", "profile_id": "generic", "offline": True})
    )

    assert [event["type"] for event in events[:-1]] == ["progress"] * (len(events) - 1)
    assert events[-1]["type"] == "result"

    result = events[-1]["result"]
    assert result["contract_version"] == "v1"
    assert result["mode"] == "offline"
    assert result["profile_id"] == "generic"
    assert result["counts"]["found"] == 4  # the four offline mock records


def test_the_stream_is_ndjson_and_uncached(run_client: TestClient) -> None:
    response = run_client.post(
        "/api/run", json={"question": "coating", "profile_id": "generic", "offline": True}
    )

    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-cache"


def test_an_empty_question_runs_the_profile_default(run_client: TestClient) -> None:
    events = _events(
        run_client.post("/api/run", json={"question": "", "profile_id": "generic", "offline": True})
    )

    assert events[-1]["result"]["question"] == "fallback question"


def test_the_client_request_id_is_echoed_back(run_client: TestClient) -> None:
    events = _events(
        run_client.post(
            "/api/run",
            json={"question": "coating", "profile_id": "generic", "offline": True, "request_id": "req_ui_1"},
        )
    )

    assert events[-1]["result"]["request_id"] == "req_ui_1"


def test_a_pipeline_failure_is_streamed_as_an_error_event_not_a_500(
    run_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(run_client.app.state.search_service, "run", boom)

    events = _events(
        run_client.post("/api/run", json={"question": "coating", "profile_id": "generic", "offline": True})
    )

    assert events[-1] == {"type": "error", "error": "pipeline exploded"}


def test_an_unknown_profile_arrives_as_a_stream_error_not_a_status_code(run_client: TestClient) -> None:
    """Streaming caveat: headers are already sent, so a mid-run failure cannot
    become a 404. The profile is resolved inside the worker thread, so the UI
    must read the last event, not just the HTTP status.
    """
    response = run_client.post(
        "/api/run", json={"question": "coating", "profile_id": "ghost", "offline": True}
    )

    assert response.status_code == 200
    assert _events(response)[-1] == {"type": "error", "error": "Unknown profile 'ghost'"}
