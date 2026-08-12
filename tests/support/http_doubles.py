"""In-memory stand-ins for `requests` objects.

`core.util.http` and `HttpProfileRepository` only touch a handful of attributes
on a response (`status_code`, `headers`, `reason`, `text`, `.json()`), so a tiny
fake is enough and keeps unit tests free of sockets.
"""

from __future__ import annotations

from typing import Any

import requests

JSON_HEADERS = {"Content-Type": "application/json"}


class FakeResponse:
    """Minimal `requests.Response` look-alike."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Any | None = None,
        json_error: Exception | None = None,
        headers: dict[str, str] | None = None,
        reason: str = "",
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error
        # Default to a JSON content type: `request_json` refuses to parse a
        # response that does not look like JSON.
        self.headers = JSON_HEADERS if headers is None else headers
        self.reason = reason
        self.text = text

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class ScriptedSession:
    """Replays a queue of `FakeResponse` objects and records every call.

    Serves both transports used in this codebase:
    `session.get(...)` (`core.util.http`) and
    `session.request(...)` (`HttpProfileRepository`).
    """

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        timeout: Any = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        return self._pop({"method": "GET", "url": url, "params": params, "timeout": timeout, "headers": headers})

    def request(
        self,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        timeout: Any = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        return self._pop({"method": method, "url": url, "json": json, "timeout": timeout, "headers": headers})

    def _pop(self, call: dict[str, Any]) -> FakeResponse:
        self.calls.append(call)
        if not self._responses:
            raise AssertionError(f"ScriptedSession ran out of responses at call {len(self.calls)}: {call}")
        return self._responses.pop(0)


class RaisingSession:
    """Session whose every call raises `exc` — for transport-failure paths."""

    def __init__(self, exc: Exception, *, calls_before_success: int = 0, success: FakeResponse | None = None) -> None:
        self._exc = exc
        self._remaining_failures = calls_before_success
        self._success = success
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params=None, timeout=None, headers=None) -> FakeResponse:
        return self._next({"method": "GET", "url": url, "params": params})

    def request(self, method: str, url: str, json=None, timeout=None, headers=None) -> FakeResponse:
        return self._next({"method": method, "url": url, "json": json})

    def _next(self, call: dict[str, Any]) -> FakeResponse:
        self.calls.append(call)
        if self._remaining_failures > 0 or self._success is None:
            self._remaining_failures -= 1
            raise self._exc
        return self._success
