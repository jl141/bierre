"""Run settings, loaded from an optional YAML file.

Every field has a default, so the pipeline runs with no config file at all.
A ``config.yaml`` (see ``config.example.yaml``) overrides any subset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ALL_SOURCES = ["openalex", "crossref", "pubmed", "europepmc", "semantic_scholar"]


@dataclass
class SearchSettings:
    max_results_per_query: int = 10
    max_queries_per_run: int = 12
    concurrent_workers: int = 8
    timeout_seconds: int = 20
    enabled_sources: list[str] = field(default_factory=lambda: list(ALL_SOURCES))
    # Semantic Scholar is rate-limited hard without a key; cap anonymous queries.
    semantic_scholar_max_queries_without_key: int = 0
    # Optional per-stage HTTP override knobs consumed by SearchContext.http_options.
    source_http_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class SelectionSettings:
    enabled: bool = True
    top_n: int = 25
    min_relevance: float = 30.0


@dataclass
class Settings:
    profile: str = "generic"
    contact_email: str = ""
    use_unpaywall: bool = False
    api_keys: dict[str, str] = field(default_factory=dict)
    search: SearchSettings = field(default_factory=SearchSettings)
    selection: SelectionSettings = field(default_factory=SelectionSettings)

    def api_key(self, source: str) -> str:
        return str(self.api_keys.get(source) or "").strip()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        data = data or {}
        search = {**(data.get("search") or {})}
        selection = {**(data.get("selection") or {})}
        return cls(
            profile=data.get("profile", cls.profile),
            contact_email=str(data.get("contact_email") or "").strip(),
            use_unpaywall=bool(data.get("use_unpaywall", False)),
            api_keys=dict(data.get("api_keys") or {}),
            search=SearchSettings(**{k: v for k, v in search.items() if k in SearchSettings.__annotations__}),
            selection=SelectionSettings(
                **{k: v for k, v in selection.items() if k in SelectionSettings.__annotations__}
            ),
        )

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        """Load settings from ``path`` (or return all-defaults if absent)."""
        if path and Path(path).exists():
            with open(path, "r", encoding="utf-8") as handle:
                return cls.from_dict(yaml.safe_load(handle) or {})
        return cls()
