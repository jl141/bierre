"""Unit tests for `HttpProfileRepository` with a scripted transport.

The end-to-end behaviour against a real socket lives in
`tests/integration/test_http_profile_repository_api.py`.
"""

from __future__ import annotations

import pytest
import requests

from core.repositories.http_profile_repository import HttpProfileRepository, _RetryPolicy
from core.repositories.profile_repository import (
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileStoreError,
    ProfileValidationError,
    ProtectedProfileError,
)
from tests.support.http_doubles import FakeResponse, RaisingSession, ScriptedSession


def _repo(session, **kwargs) -> HttpProfileRepository:
    kwargs.setdefault("retry_policy", _RetryPolicy(max_attempts=2, backoff_base_seconds=0, backoff_max_seconds=0))
    return HttpProfileRepository(base_url="https://example.org", session=session, **kwargs)


def test_base_url_is_required() -> None:
    with pytest.raises(ValueError, match="base_url is required"):
        HttpProfileRepository(base_url="   ")


def test_list_profiles_parses_metadata() -> None:
    session = ScriptedSession(
        [
            FakeResponse(
                json_data={
                    "profiles_meta": [
                        {
                            "id": "generic",
                            "label": "Generic",
                            "created_at": "2026-08-06T00:00:00+00:00",
                            "updated_at": "2026-08-06T00:00:00+00:00",
                            "is_builtin": True,
                        }
                    ]
                }
            )
        ]
    )

    listed = _repo(session).list_profiles()

    assert len(listed) == 1
    assert listed[0].profile_id == "generic"
    assert listed[0].is_builtin is True
    assert session.calls[0]["url"] == "https://example.org/api/profiles"


def test_list_profiles_rejects_a_malformed_payload() -> None:
    session = ScriptedSession([FakeResponse(json_data={"profiles_meta": "nope"})])

    with pytest.raises(ProfileStoreError, match="profiles_meta must be a list"):
        _repo(session).list_profiles()


def test_get_profile_unwraps_the_profile_object() -> None:
    session = ScriptedSession([FakeResponse(json_data={"id": "generic", "profile": {"label": "Generic"}})])

    assert _repo(session).get_profile("generic") == {"label": "Generic"}


def test_get_profile_rejects_a_response_without_a_profile_object() -> None:
    session = ScriptedSession([FakeResponse(json_data={"id": "generic"})])

    with pytest.raises(ProfileStoreError, match="profile object missing"):
        _repo(session).get_profile("generic")


def test_write_operations_use_the_right_verbs_and_paths() -> None:
    session = ScriptedSession(
        [
            FakeResponse(status_code=201, json_data={"id": "x", "profile": {}}),
            FakeResponse(json_data={"id": "x", "profile": {}}),
            FakeResponse(json_data={"deleted": "x"}),
        ]
    )
    repo = _repo(session, headers={"Authorization": "Bearer t"})

    repo.create_profile({"label": "X"})
    repo.update_profile("x", {"label": "Y"})
    repo.delete_profile("x")

    assert [(call["method"], call["url"]) for call in session.calls] == [
        ("POST", "https://example.org/api/profiles"),
        ("PUT", "https://example.org/api/profiles/x"),
        ("DELETE", "https://example.org/api/profiles/x"),
    ]
    assert all(call["headers"] == {"Authorization": "Bearer t"} for call in session.calls)


def test_a_retryable_status_is_retried_then_succeeds(monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("core.repositories.http_profile_repository.time.sleep", sleeps.append)
    session = ScriptedSession(
        [
            FakeResponse(status_code=503, json_data={"error": "busy"}, reason="Service Unavailable"),
            FakeResponse(json_data={"id": "new", "profile": {"label": "x"}}),
        ]
    )

    created = _repo(session).create_profile({"label": "x"})

    assert created["id"] == "new"
    assert session.call_count == 2
    assert len(sleeps) == 1


def test_retries_are_bounded_and_the_last_status_is_mapped(monkeypatch) -> None:
    monkeypatch.setattr("core.repositories.http_profile_repository.time.sleep", lambda _d: None)
    session = ScriptedSession([FakeResponse(status_code=503, reason="Service Unavailable")] * 2)

    with pytest.raises(ProfileStoreError, match="HTTP 503"):
        _repo(session).list_profiles()

    assert session.call_count == 2


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, ProfileValidationError),
        (403, ProtectedProfileError),
        (404, ProfileNotFoundError),
        (409, ProfileConflictError),
        (418, ProfileStoreError),
    ],
)
def test_http_status_codes_map_onto_domain_errors(status, expected) -> None:
    session = ScriptedSession([FakeResponse(status_code=status, json_data={"error": "boom"})])

    with pytest.raises(expected, match="boom"):
        _repo(session).get_profile("x")


def test_the_reason_phrase_is_used_when_the_body_has_no_error_field() -> None:
    session = ScriptedSession([FakeResponse(status_code=404, json_error=ValueError("no json"), reason="Not Found")])

    with pytest.raises(ProfileNotFoundError, match="Not Found"):
        _repo(session).get_profile("x")


def test_a_non_json_success_body_is_an_error() -> None:
    session = ScriptedSession([FakeResponse(json_error=ValueError("nope"))])

    with pytest.raises(ProfileStoreError, match="not valid JSON"):
        _repo(session).list_profiles()


def test_a_json_array_response_is_rejected() -> None:
    session = ScriptedSession([FakeResponse(json_data=["not", "an", "object"])])

    with pytest.raises(ProfileStoreError, match="must be a JSON object"):
        _repo(session).list_profiles()


def test_transport_failures_surface_as_store_errors(monkeypatch) -> None:
    monkeypatch.setattr("core.repositories.http_profile_repository.time.sleep", lambda _d: None)
    session = RaisingSession(requests.ConnectionError("refused"))

    with pytest.raises(ProfileStoreError, match="request failed: refused"):
        _repo(session).list_profiles()

    assert len(session.calls) == 2  # retried once
