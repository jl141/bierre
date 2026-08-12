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
DEPLOYMENT_MODES = ("local", "hosted")
AUTH_METHODS = ("magic_link", "password", "google", "orcid")


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
class ProfileRepositorySettings:
    mode: str = "local"
    base_url: str = ""
    timeout_seconds: int = 20
    max_attempts: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 4.0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class DeploymentSettings:
    """Which run mode this process serves, and how it verifies account tokens.

    The mode is declared, never inferred: a hosted deployment that failed to say
    so would fall back to local rules and hand anonymous callers write access to
    every profile, so an unrecognised value is a start-up failure instead.
    """

    mode: str = "local"
    accounts_base: str = "/accounts"
    auth_methods: list[str] = field(default_factory=lambda: ["password"])
    token_issuer: str = "https://bierre.ca/accounts"
    token_audience: str = "bierre-api"

    def __post_init__(self) -> None:
        if self.mode not in DEPLOYMENT_MODES:
            raise ValueError(f"deployment.mode must be one of {list(DEPLOYMENT_MODES)}, got {self.mode!r}")
        unknown = [method for method in self.auth_methods if method not in AUTH_METHODS]
        if unknown:
            raise ValueError(f"deployment.auth_methods has unknown entries: {unknown}")
        self.accounts_base = "/" + str(self.accounts_base or "").strip().strip("/")

    @property
    def is_hosted(self) -> bool:
        return self.mode == "hosted"

    @property
    def jwks_path(self) -> str:
        return f"{self.accounts_base}/.well-known/jwks.json"


@dataclass
class Settings:
    profile: str = "generic"
    contact_email: str = ""
    use_unpaywall: bool = False
    api_keys: dict[str, str] = field(default_factory=dict)
    search: SearchSettings = field(default_factory=SearchSettings)
    selection: SelectionSettings = field(default_factory=SelectionSettings)
    profile_repository: ProfileRepositorySettings = field(default_factory=ProfileRepositorySettings)
    deployment: DeploymentSettings = field(default_factory=DeploymentSettings)

    def api_key(self, source: str) -> str:
        return str(self.api_keys.get(source) or "").strip()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        data = data or {}
        search = {**(data.get("search") or {})}
        selection = {**(data.get("selection") or {})}
        profile_repository = {**(data.get("profile_repository") or {})}
        deployment = {**(data.get("deployment") or {})}
        return cls(
            profile=data.get("profile", cls.profile),
            contact_email=str(data.get("contact_email") or "").strip(),
            use_unpaywall=bool(data.get("use_unpaywall", False)),
            api_keys=dict(data.get("api_keys") or {}),
            search=SearchSettings(**{k: v for k, v in search.items() if k in SearchSettings.__annotations__}),
            selection=SelectionSettings(
                **{k: v for k, v in selection.items() if k in SelectionSettings.__annotations__}
            ),
            profile_repository=ProfileRepositorySettings(
                **{
                    k: v
                    for k, v in profile_repository.items()
                    if k in ProfileRepositorySettings.__annotations__
                }
            ),
            deployment=DeploymentSettings(
                **{k: v for k, v in deployment.items() if k in DeploymentSettings.__annotations__}
            ),
        )

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        """Load settings from ``path`` (or return all-defaults if absent)."""
        if path and Path(path).exists():
            with open(path, "r", encoding="utf-8") as handle:
                return cls.from_dict(yaml.safe_load(handle) or {})
        return cls()
