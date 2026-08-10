"""Unit tests for `ProfileService` — a thin, transport-agnostic pass-through."""

from __future__ import annotations

import pytest

from core.repositories.profile_repository import ProfileNotFoundError, ProfileSummary
from core.services.profile_service import ProfileService


class FakeProfileRepository:
    def __init__(self) -> None:
        self.created_payload: dict | None = None
        self.updated_payload: tuple[str, dict] | None = None
        self.deleted_profile_id: str | None = None

    def list_profiles(self) -> list[ProfileSummary]:
        return [
            ProfileSummary(
                profile_id="generic",
                label="Generic",
                created_at="2026-08-06T00:00:00+00:00",
                updated_at="2026-08-06T00:00:00+00:00",
                is_builtin=True,
            )
        ]

    def get_profile(self, profile_id: str) -> dict:
        if profile_id == "missing":
            raise ProfileNotFoundError("Unknown profile 'missing'")
        return {"name": profile_id, "label": "Profile"}

    def create_profile(self, payload: dict) -> dict:
        self.created_payload = payload
        return {"id": "new-profile", "profile": payload}

    def update_profile(self, profile_id: str, payload: dict) -> dict:
        self.updated_payload = (profile_id, payload)
        return {"id": profile_id, "profile": payload}

    def delete_profile(self, profile_id: str) -> None:
        self.deleted_profile_id = profile_id


@pytest.fixture
def repo() -> FakeProfileRepository:
    return FakeProfileRepository()


def test_every_operation_delegates_to_the_repository(repo: FakeProfileRepository) -> None:
    service = ProfileService(repository=repo)

    assert service.list_profiles()[0].profile_id == "generic"
    assert service.get_profile("generic")["name"] == "generic"
    assert service.create_profile({"label": "X"})["id"] == "new-profile"
    assert service.update_profile("generic", {"label": "Y"})["id"] == "generic"
    service.delete_profile("generic")

    assert repo.created_payload == {"label": "X"}
    assert repo.updated_payload == ("generic", {"label": "Y"})
    assert repo.deleted_profile_id == "generic"


def test_repository_errors_propagate_untranslated(repo: FakeProfileRepository) -> None:
    """The web layer maps domain errors to status codes; the service must not swallow them."""
    with pytest.raises(ProfileNotFoundError):
        ProfileService(repository=repo).get_profile("missing")


def test_the_default_repository_is_the_local_yaml_one() -> None:
    from core.repositories.yaml_profile_repository import YamlProfileRepository

    assert isinstance(ProfileService()._repository, YamlProfileRepository)
