"""Service layer for profile CRUD backed by a ProfileRepository."""

from __future__ import annotations

from ..profile_store import ProfileSummary
from ..repositories.profile_repository import ProfileRepository
from ..repositories.yaml_profile_repository import YamlProfileRepository


class ProfileService:
    """Centralizes profile operations so adapters stay transport-thin."""

    def __init__(self, repository: ProfileRepository | None = None) -> None:
        self._repository = repository or YamlProfileRepository()

    def list_profiles(self) -> list[ProfileSummary]:
        return self._repository.list_profiles()

    def get_profile(self, profile_id: str) -> dict:
        return self._repository.get_profile(profile_id)

    def create_profile(self, payload: dict) -> dict:
        return self._repository.create_profile(payload)

    def update_profile(self, profile_id: str, payload: dict) -> dict:
        return self._repository.update_profile(profile_id, payload)

    def delete_profile(self, profile_id: str) -> None:
        self._repository.delete_profile(profile_id)
