"""Service layer for canonical run/search orchestration."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..contracts.run_search import RunSearchRequest, RunSearchResponse, map_run_result_to_response
from ..models import RunResult
from ..pipeline import ProgressCallback, run_pipeline
from ..repositories.profile_repository import DomainProfile
from ..repositories.yaml_profile_repository import YamlProfileRepository


def _load_profile_from_repository(profile_id: str) -> DomainProfile:
    payload = YamlProfileRepository().get_profile(profile_id)
    return DomainProfile.from_dict(payload)


@dataclass
class SearchService:
    """Single run/search entrypoint used by all adapters."""

    # Settings in search/selection config that can be updated by the frontend
    _ALLOWED = ["max_results_per_query", "max_queries_per_run", "concurrent_workers",
                "timeout_seconds", "enabled_sources", "enabled", "top_n", "min_relevance"]

    base_settings: Settings
    profile_loader: Callable[[str], DomainProfile] = _load_profile_from_repository
    pipeline_runner: Callable[..., RunResult] = run_pipeline

    def run(self, request: RunSearchRequest, progress: ProgressCallback | None = None) -> RunSearchResponse:
        settings = self._merge_settings(self.base_settings, request.settings_overrides)
        profile_id = request.profile_id or settings.profile
        profile = self.profile_loader(profile_id)
        request_id = request.request_id or self._new_request_id()

        result = self.pipeline_runner(
            question=request.question,
            settings=settings,
            profile=profile,
            offline=request.offline,
            progress=progress,
        )
        return map_run_result_to_response(result, request_id=request_id, settings=settings)

    @staticmethod
    def _new_request_id() -> str:
        return f"req_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _settings_to_dict(settings: Settings) -> dict[str, Any]:
        return {
            "profile": settings.profile,
            "contact_email": settings.contact_email,
            "use_unpaywall": settings.use_unpaywall,
            "api_keys": dict(settings.api_keys),
            "search": {
                "max_results_per_query": settings.search.max_results_per_query,
                "max_queries_per_run": settings.search.max_queries_per_run,
                "concurrent_workers": settings.search.concurrent_workers,
                "timeout_seconds": settings.search.timeout_seconds,
                "enabled_sources": list(settings.search.enabled_sources),
                "semantic_scholar_max_queries_without_key": settings.search.semantic_scholar_max_queries_without_key,
                "source_http_overrides": dict(settings.search.source_http_overrides),
            },
            "selection": {
                "enabled": settings.selection.enabled,
                "top_n": settings.selection.top_n,
                "min_relevance": settings.selection.min_relevance,
            },
        }

    @classmethod
    def _safe_update(cls, base: dict, base_key: str, overrides: dict | Any):
        for key, value in overrides.items():
            if key in cls._ALLOWED and value < base.get(base_key).get(key):
                base.get(base_key)[key] = value

    @classmethod
    def _merge_settings(cls, base: Settings, overrides: dict[str, Any]) -> Settings:
        if not overrides:
            return base
        if not isinstance(overrides, dict):
            raise ValueError("settings_overrides must be an object")

        merged = cls._settings_to_dict(base)
        for key, value in overrides.items():
            if key in {"api_keys"} and isinstance(value, dict):
                merged.setdefault(key, {}).update(value)
            elif key in {"search", "selection"} and isinstance(value, dict):
                cls._safe_update(merged, key, value)
            else:
                merged[key] = value
        return Settings.from_dict(merged)
