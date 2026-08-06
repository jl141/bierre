"""Repository contract + transport-agnostic profile domain types."""

from __future__ import annotations

from dataclasses import dataclass
from abc import ABC, abstractmethod


class ProfileStoreError(Exception):
    """Base error for profile storage operations."""


class ProfileValidationError(ProfileStoreError):
    """Payload or id does not satisfy schema/safety requirements."""


class ProfileNotFoundError(ProfileStoreError):
    """Requested profile does not exist."""


class ProfileConflictError(ProfileStoreError):
    """Create operation conflicts with an existing profile id."""


class ProtectedProfileError(ProfileStoreError):
    """Operation targets a protected built-in profile."""


@dataclass(frozen=True)
class ProfileSummary:
    profile_id: str
    label: str
    created_at: str
    updated_at: str
    is_builtin: bool

    def to_dict(self) -> dict:
        return {
            "id": self.profile_id,
            "label": self.label,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_builtin": self.is_builtin,
        }


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
