"""bierre core: a profile-driven literature search and triage library.

Public surface kept small on purpose — adapters (CLI, web, future API/service)
should depend only on these names:

    from core import run_pipeline, Settings, load_profile, available_profiles
"""

from __future__ import annotations

from .config import Settings
from .pipeline import run_pipeline
from .profiles import DomainProfile, available_profiles, load_profile

__all__ = [
    "run_pipeline",
    "Settings",
    "DomainProfile",
    "load_profile",
    "available_profiles",
]
