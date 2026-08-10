"""Fixtures for tests that wire several real components together."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from core.config import Settings
from core.repositories.yaml_profile_repository import YamlProfileRepository
from core.services.profile_service import ProfileService
from core.services.search_service import SearchService
from tests.factories import profile_payload


@pytest.fixture
def seeded_profiles_dir(profiles_dir: Path) -> Path:
    """A temporary profiles directory containing a usable `generic` profile."""
    YamlProfileRepository(profiles_dir).create_profile(
        profile_payload(name="generic", label="Generic", default_question="default question")
    )
    return profiles_dir


@pytest.fixture
def app_settings() -> Settings:
    return Settings.from_dict({"profile": "generic", "search": {"enabled_sources": []}})


@pytest.fixture
def api_client(seeded_profiles_dir: Path, app_settings: Settings) -> Iterator[TestClient]:
    """A `TestClient` over the real ASGI app, backed by a temporary profiles dir.

    `create_app` wires a repository pointed at the checked-in `profiles/`
    directory, so both services on `app.state` are swapped for temp-dir ones
    before any request runs.
    """
    from webapp import server

    app = server.create_app(app_settings)
    profile_service = ProfileService(repository=YamlProfileRepository(seeded_profiles_dir))
    app.state.profile_service = profile_service
    app.state.search_service = SearchService(
        base_settings=app_settings,
        profile_loader=server._profile_loader(profile_service),
    )

    with TestClient(app) as client:
        yield client


@pytest.fixture
def writable_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lift the read-only guard that blocks profile mutation by default."""
    monkeypatch.setenv("BIERRE_READONLY", "0")
