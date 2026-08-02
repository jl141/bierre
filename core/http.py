"""The single network dependency, isolated from the pure pipeline logic.

Search sources are the only part of the core that touches the network. Keeping
that here means ranking/planning/extraction stay deterministic and testable.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Any
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
) -> float:
    if retry_after_seconds is not None:
        return min(retry_after_seconds, backoff_max_seconds)
    exponential = backoff_base_seconds * (2 ** max(attempt - 1, 0))
    jitter = _jitter_random() * backoff_base_seconds
    return min(backoff_max_seconds, exponential + jitter)


def _appears_json_response(response: requests.Response) -> bool:
    content_type = str((response.headers or {}).get("Content-Type") or "").lower()
    if "json" in content_type or "+json" in content_type:
        return True
    snippet = (response.text or "").lstrip()[:1]
    return snippet in {"{", "[", '"', "t", "f", "n", "-"} or snippet.isdigit()


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
) -> Any | None:
    """GET ``url`` and return parsed JSON, or ``None`` on any failure.

    Network and parse failures are recorded in ``errors`` rather than raised, so
    one flaky source never aborts the whole run.
    """
    merged_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    resolved_max_attempts = max(1, int(max_attempts or DEFAULT_MAX_ATTEMPTS))
    resolved_backoff_base = float(backoff_base_seconds or DEFAULT_BACKOFF_BASE_SECONDS)
    resolved_backoff_max = float(backoff_max_seconds or DEFAULT_BACKOFF_MAX_SECONDS)
    resolved_retryable_statuses = _normalize_retryable_status_codes(retryable_status_codes)
    safe_url = _redact_url(url, params)
    session = _get_session()
    start_time = time.monotonic()

    for attempt in range(1, resolved_max_attempts + 1):
        try:
            response = session.get(url, params=params, timeout=timeout, headers=merged_headers)
        except requests.RequestException as exc:
            retryable = isinstance(exc, RETRYABLE_EXCEPTION_TYPES)
            if retryable and attempt < resolved_max_attempts:
                _sleep(_retry_delay_seconds(attempt, None, resolved_backoff_base, resolved_backoff_max))
                continue
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            record_error(
                errors,
                stage,
                str(exc),
                "network_or_api_error",
                url=safe_url,
                status_code=None,
                reason=None,
                retryable=retryable,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
            )
            return None

        status_code = response.status_code
        reason = getattr(response, "reason", "") or ""
        retry_after = _parse_retry_after(response.headers)
        if _is_retryable_status(status_code, resolved_retryable_statuses):
            if attempt < resolved_max_attempts:
                _sleep(
                    _retry_delay_seconds(
                        attempt,
                        retry_after,
                        resolved_backoff_base,
                        resolved_backoff_max,
                    )
                )
                continue
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            record_error(
                errors,
                stage,
                f"HTTP {status_code}: {reason}",
                "network_or_api_error",
                url=safe_url,
                status_code=status_code,
                reason=reason,
                retryable=True,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
            )
            return None

        if status_code >= 400:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            record_error(
                errors,
                stage,
                f"HTTP {status_code}: {reason}",
                "network_or_api_error",
                url=safe_url,
                status_code=status_code,
                reason=reason,
                retryable=False,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
            )
            return None

        if not _appears_json_response(response):
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            record_error(
                errors,
                stage,
                "Response does not appear to be JSON.",
                "json_parse_error",
                url=safe_url,
                status_code=status_code,
                reason=reason,
                retryable=False,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
                content_type=str((response.headers or {}).get("Content-Type") or ""),
            )
            return None

        try:
            return response.json()
        except ValueError as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            record_error(
                errors,
                stage,
                str(exc),
                "json_parse_error",
                url=safe_url,
                status_code=status_code,
                reason=reason,
                retryable=False,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
            )
            return None
    return None


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
) -> str | None:
    """GET ``url`` and return response text, or ``None`` on any failure."""
    merged_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    resolved_max_attempts = max(1, int(max_attempts or DEFAULT_MAX_ATTEMPTS))
    resolved_backoff_base = float(backoff_base_seconds or DEFAULT_BACKOFF_BASE_SECONDS)
    resolved_backoff_max = float(backoff_max_seconds or DEFAULT_BACKOFF_MAX_SECONDS)
    resolved_retryable_statuses = _normalize_retryable_status_codes(retryable_status_codes)
    safe_url = _redact_url(url, params)
    session = _get_session()
    start_time = time.monotonic()

    for attempt in range(1, resolved_max_attempts + 1):
        try:
            response = session.get(url, params=params, timeout=timeout, headers=merged_headers)
        except requests.RequestException as exc:
            retryable = isinstance(exc, RETRYABLE_EXCEPTION_TYPES)
            if retryable and attempt < resolved_max_attempts:
                _sleep(_retry_delay_seconds(attempt, None, resolved_backoff_base, resolved_backoff_max))
                continue
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            record_error(
                errors,
                stage,
                str(exc),
                "network_or_api_error",
                url=safe_url,
                status_code=None,
                reason=None,
                retryable=retryable,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
            )
            return None

        status_code = response.status_code
        reason = getattr(response, "reason", "") or ""
        retry_after = _parse_retry_after(response.headers)
        if _is_retryable_status(status_code, resolved_retryable_statuses):
            if attempt < resolved_max_attempts:
                _sleep(
                    _retry_delay_seconds(
                        attempt,
                        retry_after,
                        resolved_backoff_base,
                        resolved_backoff_max,
                    )
                )
                continue
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            record_error(
                errors,
                stage,
                f"HTTP {status_code}: {reason}",
                "network_or_api_error",
                url=safe_url,
                status_code=status_code,
                reason=reason,
                retryable=True,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
            )
            return None

        if status_code >= 400:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            record_error(
                errors,
                stage,
                f"HTTP {status_code}: {reason}",
                "network_or_api_error",
                url=safe_url,
                status_code=status_code,
                reason=reason,
                retryable=False,
                attempt_count=attempt,
                elapsed_ms=elapsed_ms,
            )
            return None

        return response.text
    return None
