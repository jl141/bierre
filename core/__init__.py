"""bierre core: a profile-driven literature search and triage library.

Public surface kept small on purpose — adapters (CLI, web, future API/service)
should depend only on these names:

    from core import run_pipeline, Settings
"""

from __future__ import annotations

from .config import Settings
from .contracts import RunSearchRequest, RunSearchResponse
from .pipeline import run_pipeline
from .repositories import (
    DomainProfile,
    HttpProfileRepository,
    ProfileRepository,
    YamlProfileRepository,
    build_profile_repository,
)
from .services import ProfileService, SearchService

__all__ = [
    "run_pipeline",
    "Settings",
    "DomainProfile",
    "RunSearchRequest",
    "RunSearchResponse",
    "ProfileRepository",
    "YamlProfileRepository",
    "HttpProfileRepository",
    "build_profile_repository",
    "ProfileService",
    "SearchService",
]
