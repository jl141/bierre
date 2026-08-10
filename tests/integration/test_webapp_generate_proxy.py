"""The `/bierre-ca/api/profiles/generate` proxy.

bierre-ca is a separate service, so the upstream `requests.post` call is stubbed
here; what is under test is the proxy's own streaming and error mapping.
"""

from __future__ import annotations

import json

import pytest
import requests
from fastapi.testclient import TestClient

from webapp import server

PAYLOAD = {"research_description": "microplastics and human health"}


def _events(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


class _UpstreamResponse:
    def __init__(self, *, status_code: int = 200, payload=None, content: bytes = b"{}") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch):
    """Replace the outbound call to bierre-ca; returns the recorded request."""
    recorded: dict = {}

    def install(response=None, exc: Exception | None = None):
        def fake_post(url, json=None, headers=None, timeout=None):
            recorded.update(url=url, json=json, headers=headers, timeout=timeout)
            if exc is not None:
                raise exc
            return response

        monkeypatch.setattr(server.requests, "post", fake_post)
        return recorded

    return install


def test_a_successful_generation_streams_progress_then_the_result(api_client: TestClient, upstream) -> None:
    upstream(_UpstreamResponse(payload={"profile": {"label": "Microplastics"}}))

    events = _events(api_client.post("/bierre-ca/api/profiles/generate", json=PAYLOAD))

    assert [event["type"] for event in events] == ["progress", "progress", "progress", "result"]
    assert events[-1]["result"] == {"profile": {"label": "Microplastics"}}


def test_the_upstream_url_and_api_key_come_from_the_environment(
    api_client: TestClient, upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BIERRE_CA_BASE_URL", "http://ca.internal:9000/")
    monkeypatch.setenv("BIERRE_CA_API_KEY", "secret-key")
    recorded = upstream(_UpstreamResponse())

    api_client.post("/bierre-ca/api/profiles/generate", json={**PAYLOAD, "label_hint": "MP"})

    assert recorded["url"] == "http://ca.internal:9000/api/profiles/generate"
    assert recorded["headers"]["X-API-Key"] == "secret-key"
    assert recorded["json"] == {"research_description": PAYLOAD["research_description"], "label_hint": "MP"}


def test_an_upstream_error_response_becomes_an_error_event(api_client: TestClient, upstream) -> None:
    upstream(_UpstreamResponse(status_code=422, payload={"detail": "description too vague"}))

    events = _events(api_client.post("/bierre-ca/api/profiles/generate", json=PAYLOAD))

    assert events[-1] == {"type": "error", "error": "description too vague"}


def test_an_unreachable_service_becomes_an_error_event(api_client: TestClient, upstream) -> None:
    upstream(exc=requests.ConnectionError("connection refused"))

    events = _events(api_client.post("/bierre-ca/api/profiles/generate", json=PAYLOAD))

    assert events[-1]["type"] == "error"
    assert "Cannot reach bierre-ca service" in events[-1]["error"]


def test_a_malformed_upstream_body_becomes_an_error_event(api_client: TestClient, upstream) -> None:
    upstream(_UpstreamResponse(payload=ValueError("no json"), content=b"<html>"))

    events = _events(api_client.post("/bierre-ca/api/profiles/generate", json=PAYLOAD))

    assert events[-1] == {"type": "error", "error": "bierre-ca returned a malformed response"}


def test_an_empty_research_description_is_rejected(api_client: TestClient) -> None:
    response = api_client.post("/bierre-ca/api/profiles/generate", json={"research_description": ""})

    assert response.status_code == 400
    assert "research_description" in response.json()["error"]
