"""Shared context object passed to every search source."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchContext:
    """Per-run knobs and shared error sink handed to each source."""

    max_results: int = 10
    timeout: int = 20
    email: str = ""
    api_keys: dict[str, str] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def api_key(self, source: str) -> str:
        return str(self.api_keys.get(source) or "").strip()
