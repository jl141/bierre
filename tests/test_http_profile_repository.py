from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.profile_store import ProfileNotFoundError, ProfileValidationError
from core.repositories.http_profile_repository import HttpProfileRepository, _RetryPolicy


class FakeResponse:
    def __init__(self, *, status_code: int, payload: dict | None = None, reason: str = "") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.reason = reason

    def json(self):
        return self._payload


class ScriptedSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def request(self, method: str, url: str, json: dict | None, timeout: int, headers: dict):
        self.calls.append({"method": method, "url": url, "json": json, "timeout": timeout, "headers": headers})
        if not self._responses:
            raise AssertionError("No scripted response left")
        return self._responses.pop(0)


def test_http_profile_repository_list_profiles_parses_metadata() -> None:
    session = ScriptedSession(
        [
            FakeResponse(
                status_code=200,
                payload={
                    "profiles_meta": [
                        {
                            "id": "generic",
                            "label": "Generic",
                            "created_at": "2026-08-06T00:00:00+00:00",
                            "updated_at": "2026-08-06T00:00:00+00:00",
                            "is_builtin": True,
                        }
                    ]
                },
            )
        ]
    )
    repo = HttpProfileRepository(base_url="https://example.org", session=session)

    listed = repo.list_profiles()

    assert len(listed) == 1
    assert listed[0].profile_id == "generic"
    assert listed[0].is_builtin is True


def test_http_profile_repository_retries_then_succeeds() -> None:
    session = ScriptedSession(
        [
            FakeResponse(status_code=503, payload={"error": "busy"}, reason="Service Unavailable"),
            FakeResponse(status_code=200, payload={"id": "new", "profile": {"label": "x"}}),
        ]
    )
    repo = HttpProfileRepository(
        base_url="https://example.org",
        session=session,
        retry_policy=_RetryPolicy(max_attempts=2, backoff_base_seconds=0.1, backoff_max_seconds=0.1),
    )

    with patch("core.repositories.http_profile_repository.time.sleep") as mocked_sleep:
        created = repo.create_profile({"label": "x"})

    assert created["id"] == "new"
    assert len(session.calls) == 2
    assert mocked_sleep.call_count == 1


def test_http_profile_repository_maps_status_to_domain_errors() -> None:
    not_found_session = ScriptedSession([FakeResponse(status_code=404, payload={"error": "missing"})])
    repo_not_found = HttpProfileRepository(base_url="https://example.org", session=not_found_session)

    try:
        repo_not_found.get_profile("missing")
    except ProfileNotFoundError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Expected ProfileNotFoundError")

    bad_req_session = ScriptedSession([FakeResponse(status_code=400, payload={"error": "bad input"})])
    repo_bad_req = HttpProfileRepository(base_url="https://example.org", session=bad_req_session)

    try:
        repo_bad_req.create_profile({})
    except ProfileValidationError as exc:
        assert "bad input" in str(exc)
    else:
        raise AssertionError("Expected ProfileValidationError")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All HTTP repository tests passed.")
