"""Unit tests for `core.utils.http` — the shared retrying HTTP helpers.

`request_json` / `request_text` accept `session=`, `sleep_fn=` and `jitter_fn=`
keyword arguments purely so tests can drive them; no sockets and no real sleeps
are involved here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
import requests

from core.utils.http import (
    DEFAULT_MAX_ATTEMPTS,
    record_error,
    request_json,
    request_text,
)
from tests.support.http_doubles import FakeResponse, RaisingSession, ScriptedSession

URL = "https://api.example.org/works"


def _call_json(session, errors, sleeps=None, **kwargs):
    return request_json(
        URL,
        kwargs.pop("params", None),
        kwargs.pop("timeout", 5),
        errors,
        "test",
        session=session,
        sleep_fn=(sleeps.append if sleeps is not None else lambda _delay: None),
        jitter_fn=lambda: 0.0,
        **kwargs,
    )


# --- happy paths -------------------------------------------------------------


@pytest.mark.parametrize("payload", [{"ok": True}, [1, 2, 3], "ok", 7, None])
def test_any_valid_json_top_level_shape_is_returned(payload, errors: list[dict]) -> None:
    session = ScriptedSession([FakeResponse(json_data=payload)])

    assert _call_json(session, errors) == payload
    assert session.call_count == 1
    assert errors == []


def test_tuple_timeouts_are_forwarded_unchanged(errors: list[dict]) -> None:
    session = ScriptedSession([FakeResponse(json_data={"ok": 1})])

    _call_json(session, errors, timeout=(1, 7))

    assert session.calls[0]["timeout"] == (1, 7)


def test_request_text_returns_the_raw_body(errors: list[dict]) -> None:
    session = ScriptedSession([FakeResponse(text="<xml>ok</xml>", headers={})])

    body = request_text(URL, None, 5, errors, "test", session=session, sleep_fn=lambda _d: None)

    assert body == "<xml>ok</xml>"
    assert errors == []


# --- retries -----------------------------------------------------------------


def test_a_5xx_is_retried_with_exponential_backoff(errors: list[dict]) -> None:
    sleeps: list[float] = []
    session = ScriptedSession(
        [
            FakeResponse(status_code=503, reason="Service Unavailable"),
            FakeResponse(json_data=[1, 2, 3]),
        ]
    )

    assert _call_json(session, errors, sleeps) == [1, 2, 3]
    assert session.call_count == 2
    assert sleeps == [0.5]  # backoff_base * 2**0, jitter pinned to 0
    assert errors == []


def test_retry_after_header_wins_over_computed_backoff(errors: list[dict]) -> None:
    sleeps: list[float] = []
    session = ScriptedSession(
        [
            FakeResponse(status_code=429, reason="Too Many Requests", headers={"Retry-After": "2"}),
            FakeResponse(json_data="ok"),
        ]
    )

    assert _call_json(session, errors, sleeps) == "ok"
    assert sleeps == [2.0]


def test_retry_after_is_clamped_to_the_backoff_ceiling(errors: list[dict]) -> None:
    sleeps: list[float] = []
    session = ScriptedSession(
        [
            FakeResponse(status_code=503, headers={"Retry-After": "600"}),
            FakeResponse(json_data={"ok": True}),
        ]
    )

    _call_json(session, errors, sleeps, backoff_max_seconds=1.5)

    assert sleeps == [1.5]


def test_an_http_date_retry_after_is_converted_to_a_delay(errors: list[dict]) -> None:
    sleeps: list[float] = []
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30))
    session = ScriptedSession(
        [FakeResponse(status_code=503, headers={"Retry-After": future}), FakeResponse(json_data={"ok": 1})]
    )

    _call_json(session, errors, sleeps, backoff_max_seconds=60)

    assert 25 <= sleeps[0] <= 30


def test_an_unparseable_retry_after_falls_back_to_backoff(errors: list[dict]) -> None:
    sleeps: list[float] = []
    session = ScriptedSession(
        [FakeResponse(status_code=503, headers={"Retry-After": "soon"}), FakeResponse(json_data={"ok": 1})]
    )

    _call_json(session, errors, sleeps)

    assert sleeps == [0.5]


def test_unparseable_retryable_status_codes_fall_back_to_the_defaults(errors: list[dict]) -> None:
    sleeps: list[float] = []
    session = ScriptedSession([FakeResponse(status_code=503), FakeResponse(json_data={"ok": 1})])

    assert _call_json(session, errors, sleeps, retryable_status_codes=["nope"]) == {"ok": 1}


def test_exhausting_retries_records_a_retryable_error(errors: list[dict]) -> None:
    sleeps: list[float] = []
    session = ScriptedSession([FakeResponse(status_code=503, reason="Service Unavailable")] * DEFAULT_MAX_ATTEMPTS)

    assert _call_json(session, errors, sleeps) is None
    assert session.call_count == DEFAULT_MAX_ATTEMPTS
    assert len(sleeps) == DEFAULT_MAX_ATTEMPTS - 1
    assert errors[0]["retryable"] is True
    assert errors[0]["attempt_count"] == DEFAULT_MAX_ATTEMPTS


def test_max_attempts_of_one_disables_retrying(errors: list[dict]) -> None:
    sleeps: list[float] = []
    session = ScriptedSession([FakeResponse(status_code=503, reason="Service Unavailable")])

    assert _call_json(session, errors, sleeps, max_attempts=1) is None
    assert session.call_count == 1
    assert sleeps == []
    assert errors[0]["attempt_count"] == 1


def test_custom_retryable_status_codes_are_honoured(errors: list[dict]) -> None:
    session = ScriptedSession([FakeResponse(status_code=503, reason="Service Unavailable")])

    assert _call_json(session, errors, retryable_status_codes=[418]) is None
    assert session.call_count == 1  # 503 is no longer retryable
    assert errors[0]["retryable"] is False


def test_timeouts_and_connection_errors_are_retried(errors: list[dict]) -> None:
    sleeps: list[float] = []
    session = RaisingSession(
        requests.ConnectionError("boom"),
        calls_before_success=1,
        success=FakeResponse(json_data={"ok": True}),
    )

    assert _call_json(session, errors, sleeps) == {"ok": True}
    assert len(session.calls) == 2
    assert errors == []


def test_a_persistent_connection_error_is_recorded_not_raised(errors: list[dict]) -> None:
    session = RaisingSession(requests.Timeout("slow"))

    assert _call_json(session, errors, []) is None
    assert errors[0]["error_type"] == "network_or_api_error"
    assert errors[0]["retryable"] is True
    assert "slow" in errors[0]["message"]


def test_a_non_retryable_transport_error_stops_immediately(errors: list[dict]) -> None:
    session = RaisingSession(requests.TooManyRedirects("loop"))

    assert _call_json(session, errors, []) is None
    assert len(session.calls) == 1
    assert errors[0]["retryable"] is False


# --- failure reporting -------------------------------------------------------


def test_a_non_retryable_4xx_is_recorded_without_retrying(errors: list[dict]) -> None:
    session = ScriptedSession([FakeResponse(status_code=404, reason="Not Found")])

    assert _call_json(session, errors, params={"q": "x"}) is None
    assert session.call_count == 1
    assert errors == [
        {
            "stage": "test",
            "error_type": "network_or_api_error",
            "message": "HTTP 404: Not Found",
            "url": f"{URL}?q=x",
            "status_code": 404,
            "reason": "Not Found",
            "retryable": False,
            "attempt_count": 1,
            "elapsed_ms": errors[0]["elapsed_ms"],
        }
    ]


def test_broken_json_is_reported_as_a_parse_error(errors: list[dict]) -> None:
    session = ScriptedSession([FakeResponse(json_error=ValueError("bad json"), text="{broken")])

    assert _call_json(session, errors) is None
    assert errors[0]["error_type"] == "json_parse_error"
    assert errors[0]["url"].startswith(URL)


def test_an_html_error_page_is_rejected_before_parsing(errors: list[dict]) -> None:
    session = ScriptedSession(
        [FakeResponse(headers={"Content-Type": "text/html"}, text="<html>maintenance</html>")]
    )

    assert _call_json(session, errors) is None
    assert errors[0]["error_type"] == "json_parse_error"
    assert errors[0]["content_type"] == "text/html"


def test_error_urls_redact_credential_query_parameters(errors: list[dict]) -> None:
    session = ScriptedSession([FakeResponse(status_code=401, reason="Unauthorized")])

    _call_json(
        session,
        errors,
        params={"api_key": "super-secret", "token": "another-secret", "q": "safe"},
    )

    redacted = errors[0]["url"]
    assert "super-secret" not in redacted
    assert "another-secret" not in redacted
    assert "api_key=REDACTED" in redacted
    assert "token=REDACTED" in redacted
    assert "q=safe" in redacted


def test_record_error_shape_is_stable() -> None:
    errors: list[dict] = []

    record_error(errors, "unpaywall", "skipped", "configuration_error", url="https://x")

    assert errors == [
        {
            "stage": "unpaywall",
            "error_type": "configuration_error",
            "message": "skipped",
            "url": "https://x",
        }
    ]
