"""YAML-backed ProfileRepository implementation."""

from __future__ import annotations

from pathlib import Path

from .. import profile_store
from ..profile_store import ProfileSummary
from .profile_repository import ProfileRepository


class YamlProfileRepository(ProfileRepository):
    """Repository adapter over existing profile_store YAML CRUD helpers."""

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self._profiles_dir = profiles_dir

    def list_profiles(self) -> list[ProfileSummary]:
        return profile_store.list_profiles(self._profiles_dir)

    def get_profile(self, profile_id: str) -> dict:
        return profile_store.get_profile(profile_id, self._profiles_dir)

    def create_profile(self, payload: dict) -> dict:
        return profile_store.create_profile(payload, self._profiles_dir)

    def update_profile(self, profile_id: str, payload: dict) -> dict:
        return profile_store.update_profile(profile_id, payload, self._profiles_dir)

    def delete_profile(self, profile_id: str) -> None:
        profile_store.delete_profile(profile_id, self._profiles_dir)
