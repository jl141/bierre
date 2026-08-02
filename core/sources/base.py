"""Shared context object passed to every search source."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_HTTP_OPTION_KEYS = {
    "max_attempts",
    "backoff_base_seconds",
    "backoff_max_seconds",
    "retryable_status_codes",
}


@dataclass
class SearchContext:
    """Per-run knobs and shared error sink handed to each source."""

    max_results: int = 10
    timeout: int = 20
    email: str = ""
    api_keys: dict[str, str] = field(default_factory=dict)
    http_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def api_key(self, source: str) -> str:
        return str(self.api_keys.get(source) or "").strip()

    def http_options(self, stage: str) -> dict[str, Any]:
        """Return sanitized per-stage request overrides for HTTP helpers."""
        options = self.http_overrides.get(stage) or {}
        return {k: v for k, v in options.items() if k in _HTTP_OPTION_KEYS}
