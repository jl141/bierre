"""Repository contract for profile CRUD operations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..profile_store import ProfileSummary


class ProfileRepository(ABC):
    """Transport-agnostic profile persistence contract."""

    @abstractmethod
    def list_profiles(self) -> list[ProfileSummary]:
        raise NotImplementedError

    @abstractmethod
    def get_profile(self, profile_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def create_profile(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def update_profile(self, profile_id: str, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def delete_profile(self, profile_id: str) -> None:
        raise NotImplementedError
