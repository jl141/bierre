"""The single network dependency, isolated from the pure pipeline logic.

Search sources are the only part of the core that touches the network. Keeping
that here means ranking/planning/extraction stay deterministic and testable.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Any, Callable, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter

USER_AGENT = "bierre-literature-workflow/0.1 (+https://example.org)"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
RETRYABLE_EXCEPTION_TYPES = (requests.Timeout, requests.ConnectionError)
REDACT_QUERY_KEYS = {"api_key", "apikey", "key", "token", "access_token"}
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_BACKOFF_MAX_SECONDS = 4.0
DEFAULT_POOL_CONNECTIONS = 16

_sleep = time.sleep
_jitter_random = random.random
T = TypeVar("T")


@dataclass(frozen=True)
class _RequestRuntimeOptions:
    max_attempts: int
    backoff_base_seconds: float
    backoff_max_seconds: float
    retryable_statuses: set[int]


@dataclass(frozen=True)
class _RequestDependencies:
    session: requests.Session
    sleep_fn: Callable[[float], None]
    monotonic_fn: Callable[[], float]
    jitter_fn: Callable[[], float]


@dataclass(frozen=True)
class _RequestOutcome:
    response: requests.Response | None
    attempt_count: int
    elapsed_ms: int
    status_code: int | None
    reason: str | None
    retryable: bool
    message: str | None


class _ParseResponseError(ValueError):
    def __init__(self, message: str, error_type: str = "json_parse_error", **extra: Any) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.extra = extra


def record_error(
    errors: list[dict[str, Any]],
    stage: str,
    message: str,
    error_type: str = "workflow_error",
    **extra: Any,
) -> None:
    """Append a structured, non-fatal error to the shared ``errors`` list."""
    errors.append({"stage": stage, "error_type": error_type, "message": message, **extra})


def _build_session(pool_connections: int = DEFAULT_POOL_CONNECTIONS) -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool_connections, pool_maxsize=pool_connections, max_retries=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


@lru_cache(maxsize=1)
def _get_session() -> requests.Session:
    return _build_session()


def _is_retryable_status(status_code: int, retryable_statuses: set[int]) -> bool:
    return status_code in retryable_statuses


def _normalize_retryable_status_codes(codes: Any) -> set[int]:
    if codes is None:
        return set(RETRYABLE_STATUS_CODES)
    normalized: set[int] = set()
    for code in codes:
        try:
            normalized.add(int(code))
        except (TypeError, ValueError):
            continue
    return normalized or set(RETRYABLE_STATUS_CODES)


def _parse_retry_after(headers: Any) -> float | None:
    retry_after = str((headers or {}).get("Retry-After") or "").strip()
    if not retry_after:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        pass
    try:
        at = parsedate_to_datetime(retry_after)
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        delay = (at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delay)
    except (TypeError, ValueError, OverflowError):
        return None


def _redact_url(url: str, params: dict[str, Any] | None) -> str:
    prepared_url = requests.Request("GET", url, params=params).prepare().url or url
    split = urlsplit(prepared_url)
    redacted_pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        if key.lower() in REDACT_QUERY_KEYS:
            redacted_pairs.append((key, "REDACTED"))
        else:
            redacted_pairs.append((key, value))
    redacted_query = urlencode(redacted_pairs, doseq=True)
    return urlunsplit((split.scheme, split.netloc, split.path, redacted_query, split.fragment))


def _retry_delay_seconds(
    attempt: int,
    retry_after_seconds: float | None,
    backoff_base_seconds: float,
    backoff_max_seconds: float,
    jitter_fn: Callable[[], float],
) -> float:
    if retry_after_seconds is not None:
        return min(retry_after_seconds, backoff_max_seconds)
    exponential = backoff_base_seconds * (2 ** max(attempt - 1, 0))
    jitter = jitter_fn() * backoff_base_seconds
    return min(backoff_max_seconds, exponential + jitter)


def _appears_json_response(response: requests.Response) -> bool:
    content_type = str((response.headers or {}).get("Content-Type") or "").lower()
    if "json" in content_type or "+json" in content_type:
        return True
    snippet = (response.text or "").lstrip()[:1]
    return snippet in {"{", "[", '"', "t", "f", "n", "-"} or snippet.isdigit()


def _resolve_request_runtime_options(
    *,
    max_attempts: int | None,
    backoff_base_seconds: float | None,
    backoff_max_seconds: float | None,
    retryable_status_codes: set[int] | list[int] | tuple[int, ...] | None,
) -> _RequestRuntimeOptions:
    resolved_max_attempts = DEFAULT_MAX_ATTEMPTS if max_attempts is None else max_attempts
    resolved_backoff_base = DEFAULT_BACKOFF_BASE_SECONDS if backoff_base_seconds is None else backoff_base_seconds
    resolved_backoff_max = DEFAULT_BACKOFF_MAX_SECONDS if backoff_max_seconds is None else backoff_max_seconds
    return _RequestRuntimeOptions(
        max_attempts=max(1, int(resolved_max_attempts)),
        backoff_base_seconds=float(resolved_backoff_base),
        backoff_max_seconds=float(resolved_backoff_max),
        retryable_statuses=_normalize_retryable_status_codes(retryable_status_codes),
    )


def _resolve_request_dependencies(
    *,
    session: requests.Session | None,
    sleep_fn: Callable[[float], None] | None,
    monotonic_fn: Callable[[], float] | None,
    jitter_fn: Callable[[], float] | None,
) -> _RequestDependencies:
    return _RequestDependencies(
        session=session or _get_session(),
        sleep_fn=sleep_fn or _sleep,
        monotonic_fn=monotonic_fn or time.monotonic,
        jitter_fn=jitter_fn or _jitter_random,
    )


def _request_with_retry(
    *,
    url: str,
    params: dict[str, Any] | None,
    timeout: int | float | tuple[int | float, int | float],
    merged_headers: dict[str, str],
    runtime: _RequestRuntimeOptions,
    deps: _RequestDependencies,
) -> _RequestOutcome:
    start_time = deps.monotonic_fn()

    for attempt in range(1, runtime.max_attempts + 1):
        try:
            response = deps.session.get(url, params=params, timeout=timeout, headers=merged_headers)
        except requests.RequestException as exc:
            retryable = isinstance(exc, RETRYABLE_EXCEPTION_TYPES)
            if retryable and attempt < runtime.max_attempts:
                deps.sleep_fn(
                    _retry_delay_seconds(
                        attempt,
                        None,
                        runtime.backoff_base_seconds,
                        runtime.backoff_max_seconds,
                        deps.jitter_fn,
                    )
                )
                continue
            elapsed_ms = int((deps.monotonic_fn() - start_time) * 1000)
            return _RequestOutcome(
                response=None,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
                status_code=None,
                reason=None,
                retryable=retryable,
                message=str(exc),
            )

        status_code = response.status_code
        reason = getattr(response, "reason", "") or ""
        retry_after = _parse_retry_after(response.headers)

        if _is_retryable_status(status_code, runtime.retryable_statuses):
            if attempt < runtime.max_attempts:
                deps.sleep_fn(
                    _retry_delay_seconds(
                        attempt,
                        retry_after,
                        runtime.backoff_base_seconds,
                        runtime.backoff_max_seconds,
                        deps.jitter_fn,
                    )
                )
                continue
            elapsed_ms = int((deps.monotonic_fn() - start_time) * 1000)
            return _RequestOutcome(
                response=None,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
                status_code=status_code,
                reason=reason,
                retryable=True,
                message=f"HTTP {status_code}: {reason}",
            )

        if status_code >= 400:
            elapsed_ms = int((deps.monotonic_fn() - start_time) * 1000)
            return _RequestOutcome(
                response=None,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
                status_code=status_code,
                reason=reason,
                retryable=False,
                message=f"HTTP {status_code}: {reason}",
            )

        elapsed_ms = int((deps.monotonic_fn() - start_time) * 1000)
        return _RequestOutcome(
            response=response,
            attempt_count=attempt,
            elapsed_ms=elapsed_ms,
            status_code=status_code,
            reason=reason,
            retryable=False,
            message=None,
        )

    return _RequestOutcome(
        response=None,
        attempt_count=runtime.max_attempts,
        elapsed_ms=int((deps.monotonic_fn() - start_time) * 1000),
        status_code=None,
        reason=None,
        retryable=False,
        message="Request failed before receiving a response.",
    )


def _record_request_failure(
    *,
    errors: list[dict[str, Any]],
    stage: str,
    safe_url: str,
    outcome: _RequestOutcome,
) -> None:
    record_error(
        errors,
        stage,
        outcome.message or "Request failed.",
        "network_or_api_error",
        url=safe_url,
        status_code=outcome.status_code,
        reason=outcome.reason,
        retryable=outcome.retryable,
        attempt_count=outcome.attempt_count,
        elapsed_ms=outcome.elapsed_ms,
    )


def _request_parsed(
    *,
    url: str,
    params: dict[str, Any] | None,
    timeout: int | float | tuple[int | float, int | float],
    errors: list[dict[str, Any]],
    stage: str,
    headers: dict[str, str] | None,
    runtime: _RequestRuntimeOptions,
    deps: _RequestDependencies,
    parser: Callable[[requests.Response], T],
    parse_error_type: str,
) -> T | None:
    merged_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    safe_url = _redact_url(url, params)
    outcome = _request_with_retry(
        url=url,
        params=params,
        timeout=timeout,
        merged_headers=merged_headers,
        runtime=runtime,
        deps=deps,
    )
    if outcome.response is None:
        _record_request_failure(errors=errors, stage=stage, safe_url=safe_url, outcome=outcome)
        return None

    try:
        return parser(outcome.response)
    except _ParseResponseError as exc:
        record_error(
            errors,
            stage,
            str(exc),
            exc.error_type,
            url=safe_url,
            status_code=outcome.status_code,
            reason=outcome.reason,
            retryable=False,
            attempt_count=outcome.attempt_count,
            elapsed_ms=outcome.elapsed_ms,
            **exc.extra,
        )
        return None
    except ValueError as exc:
        record_error(
            errors,
            stage,
            str(exc),
            parse_error_type,
            url=safe_url,
            status_code=outcome.status_code,
            reason=outcome.reason,
            retryable=False,
            attempt_count=outcome.attempt_count,
            elapsed_ms=outcome.elapsed_ms,
        )
        return None


def _parse_json_payload(response: requests.Response) -> Any:
    if not _appears_json_response(response):
        raise _ParseResponseError(
            "Response does not appear to be JSON.",
            "json_parse_error",
            content_type=str((response.headers or {}).get("Content-Type") or ""),
        )
    return response.json()


def _parse_text_payload(response: requests.Response) -> str:
    return response.text


def request_json(
    url: str,
    params: dict[str, Any] | None,
    timeout: int | float | tuple[int | float, int | float],
    errors: list[dict[str, Any]],
    stage: str,
    headers: dict[str, str] | None = None,
    *,
    max_attempts: int | None = None,
    backoff_base_seconds: float | None = None,
    backoff_max_seconds: float | None = None,
    retryable_status_codes: set[int] | list[int] | tuple[int, ...] | None = None,
    session: requests.Session | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    monotonic_fn: Callable[[], float] | None = None,
    jitter_fn: Callable[[], float] | None = None,
) -> Any | None:
    """GET ``url`` and return parsed JSON, or ``None`` on any failure.

    Network and parse failures are recorded in ``errors`` rather than raised, so
    one flaky source never aborts the whole run.
    """
    runtime = _resolve_request_runtime_options(
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        backoff_max_seconds=backoff_max_seconds,
        retryable_status_codes=retryable_status_codes,
    )
    deps = _resolve_request_dependencies(
        session=session,
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
        jitter_fn=jitter_fn,
    )
    return _request_parsed(
        url=url,
        params=params,
        timeout=timeout,
        errors=errors,
        stage=stage,
        headers=headers,
        runtime=runtime,
        deps=deps,
        parser=_parse_json_payload,
        parse_error_type="json_parse_error",
    )


def request_text(
    url: str,
    params: dict[str, Any] | None,
    timeout: int | float | tuple[int | float, int | float],
    errors: list[dict[str, Any]],
    stage: str,
    headers: dict[str, str] | None = None,
    *,
    max_attempts: int | None = None,
    backoff_base_seconds: float | None = None,
    backoff_max_seconds: float | None = None,
    retryable_status_codes: set[int] | list[int] | tuple[int, ...] | None = None,
    session: requests.Session | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    monotonic_fn: Callable[[], float] | None = None,
    jitter_fn: Callable[[], float] | None = None,
) -> str | None:
    """GET ``url`` and return response text, or ``None`` on any failure."""
    runtime = _resolve_request_runtime_options(
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        backoff_max_seconds=backoff_max_seconds,
        retryable_status_codes=retryable_status_codes,
    )
    deps = _resolve_request_dependencies(
        session=session,
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
        jitter_fn=jitter_fn,
    )
    return _request_parsed(
        url=url,
        params=params,
        timeout=timeout,
        errors=errors,
        stage=stage,
        headers=headers,
        runtime=runtime,
        deps=deps,
        parser=_parse_text_payload,
        parse_error_type="response_parse_error",
    )
