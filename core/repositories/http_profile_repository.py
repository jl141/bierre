"""HTTP-backed ProfileRepository implementation for hosted profile APIs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from ..profile_store import (
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileStoreError,
    ProfileSummary,
    ProfileValidationError,
    ProtectedProfileError,
)
from .profile_repository import ProfileRepository

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRYABLE_EXCEPTIONS = (requests.Timeout, requests.ConnectionError)


@dataclass(frozen=True)
class _RetryPolicy:
    max_attempts: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 4.0


class HttpProfileRepository(ProfileRepository):
    """Repository adapter that maps hosted HTTP errors to domain errors."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: int = 20,
        retry_policy: _RetryPolicy | None = None,
        headers: dict[str, str] | None = None,
        session: requests.Session | None = None,
    ) -> None:
        base_url = str(base_url or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url is required for HttpProfileRepository")
        self._base_url = base_url
        self._timeout_seconds = max(1, int(timeout_seconds))
        self._retry_policy = retry_policy or _RetryPolicy()
        self._headers = dict(headers or {})
        self._session = session or requests.Session()

    def list_profiles(self) -> list[ProfileSummary]:
        payload = self._request("GET", "/api/profiles")
        items = payload.get("profiles_meta") or []
        if not isinstance(items, list):
            raise ProfileStoreError("Invalid response: profiles_meta must be a list")
        out: list[ProfileSummary] = []
        for item in items:
            out.append(
                ProfileSummary(
                    profile_id=str(item.get("id") or ""),
                    label=str(item.get("label") or ""),
                    created_at=str(item.get("created_at") or ""),
                    updated_at=str(item.get("updated_at") or ""),
                    is_builtin=bool(item.get("is_builtin")),
                )
            )
        return out

    def get_profile(self, profile_id: str) -> dict:
        payload = self._request("GET", f"/api/profiles/{profile_id}")
        profile = payload.get("profile")
        if not isinstance(profile, dict):
            raise ProfileStoreError("Invalid response: profile object missing")
        return profile

    def create_profile(self, payload: dict) -> dict:
        return self._request("POST", "/api/profiles", json_payload=payload)

    def update_profile(self, profile_id: str, payload: dict) -> dict:
        return self._request("PUT", f"/api/profiles/{profile_id}", json_payload=payload)

    def delete_profile(self, profile_id: str) -> None:
        self._request("DELETE", f"/api/profiles/{profile_id}")

    def _request(self, method: str, path: str, json_payload: dict | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None
        policy = self._retry_policy

        for attempt in range(1, max(1, policy.max_attempts) + 1):
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    json=json_payload,
                    timeout=self._timeout_seconds,
                    headers=self._headers,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if isinstance(exc, _RETRYABLE_EXCEPTIONS) and attempt < policy.max_attempts:
                    self._sleep_for_attempt(attempt)
                    continue
                raise ProfileStoreError(f"HTTP repository request failed: {exc}") from exc

            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < policy.max_attempts:
                self._sleep_for_attempt(attempt)
                continue

            if response.status_code >= 400:
                self._raise_mapped_error(response)

            try:
                payload = response.json()
            except ValueError as exc:
                raise ProfileStoreError("HTTP repository response was not valid JSON") from exc
            if not isinstance(payload, dict):
                raise ProfileStoreError("HTTP repository response must be a JSON object")
            return payload

        raise ProfileStoreError(f"HTTP repository request exhausted retries: {last_exc}")

    def _sleep_for_attempt(self, attempt: int) -> None:
        base = self._retry_policy.backoff_base_seconds
        max_wait = self._retry_policy.backoff_max_seconds
        delay = min(max_wait, base * (2 ** max(attempt - 1, 0)))
        time.sleep(max(0.0, float(delay)))

    @staticmethod
    def _raise_mapped_error(response: requests.Response) -> None:
        message = HttpProfileRepository._error_message(response)
        code = response.status_code
        if code == 400:
            raise ProfileValidationError(message)
        if code == 403:
            raise ProtectedProfileError(message)
        if code == 404:
            raise ProfileNotFoundError(message)
        if code == 409:
            raise ProfileConflictError(message)
        raise ProfileStoreError(f"HTTP {code}: {message}")

    @staticmethod
    def _error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
        return str(getattr(response, "reason", "") or "request failed")
