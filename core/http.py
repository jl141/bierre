"""The single network dependency, isolated from the pure pipeline logic.

Search sources are the only part of the core that touches the network. Keeping
that here means ranking/planning/extraction stay deterministic and testable.
"""

from __future__ import annotations

from typing import Any

import requests

USER_AGENT = "bierre-literature-workflow/0.1 (+https://example.org)"


def record_error(
    errors: list[dict[str, Any]],
    stage: str,
    message: str,
    error_type: str = "workflow_error",
    **extra: Any,
) -> None:
    """Append a structured, non-fatal error to the shared ``errors`` list."""
    errors.append({"stage": stage, "error_type": error_type, "message": message, **extra})


def request_json(
    url: str,
    params: dict[str, Any] | None,
    timeout: int,
    errors: list[dict[str, Any]],
    stage: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """GET ``url`` and return parsed JSON, or ``None`` on any failure.

    Network and parse failures are recorded in ``errors`` rather than raised, so
    one flaky source never aborts the whole run.
    """
    merged_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    try:
        response = requests.get(url, params=params, timeout=timeout, headers=merged_headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        record_error(errors, stage, str(exc), "network_or_api_error", url=url)
    except ValueError as exc:  # JSON decode error
        record_error(errors, stage, str(exc), "json_parse_error", url=url)
    return None
