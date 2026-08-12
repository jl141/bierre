"""Fixtures for tests that wire several real components together."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from core.config import Settings
from core.repositories.yaml_profile_repository import YamlProfileRepository
from core.services.profile_service import ProfileService
from core.services.search_service import SearchService
from tests.factories import profile_payload

SIGNED_IN_TOKEN = "signed-in-token"
SIGNED_IN_CLAIMS = {"sub": "0198c8d5-6f4a-7c3b-9d21-4f6a8b0c1d2e", "typ": "access", "sv": 1}


class StubTokenVerifier:
    """Recognises exactly one token, so a test can be signed in or not.

    The real verifier is exercised against generated Ed25519 keys in
    `tests/unit/test_access_token_verifier.py`; what the app-level tests need
    from it is only the yes/no answer.
    """

    def __init__(self, token: str = SIGNED_IN_TOKEN, claims: dict[str, Any] | None = None) -> None:
        self._token = token
        self._claims = claims or dict(SIGNED_IN_CLAIMS)

    def verify(self, token: str) -> dict[str, Any] | None:
        return dict(self._claims) if token == self._token else None


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
def hosted_settings() -> Settings:
    """Hosted mode over the YAML repository.

    Deliberately mixed: it isolates the write-authority and capability rules,
    which depend on `deployment.mode` alone, from the remote profile repository,
    which needs a live bierre-ca and has its own tests.
    """
    return Settings.from_dict(
        {"profile": "generic", "search": {"enabled_sources": []}, "deployment": {"mode": "hosted"}}
    )


@pytest.fixture
def client_factory(seeded_profiles_dir: Path) -> Callable[[Settings], Any]:
    """Build a `TestClient` over the real ASGI app for arbitrary settings.

    `create_app` wires a repository pointed at the checked-in `profiles/`
    directory, so both services on `app.state` are swapped for temp-dir ones
    before any request runs.
    """
    from webapp import server

    @contextmanager
    def build(settings: Settings) -> Iterator[TestClient]:
        app = server.create_app(settings)
        profile_service = ProfileService(repository=YamlProfileRepository(seeded_profiles_dir))
        app.state.profile_service = profile_service
        app.state.search_service = SearchService(
            base_settings=settings,
            profile_loader=server._profile_loader(profile_service),
        )
        if app.state.token_verifier is not None:
            app.state.token_verifier = StubTokenVerifier()
        with TestClient(app) as client:
            yield client

    return build


@pytest.fixture
def api_client(client_factory, app_settings: Settings) -> Iterator[TestClient]:
    with client_factory(app_settings) as client:
        yield client


@pytest.fixture
def hosted_client(client_factory, hosted_settings: Settings) -> Iterator[TestClient]:
    with client_factory(hosted_settings) as client:
        yield client


@pytest.fixture
def signed_in_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {SIGNED_IN_TOKEN}"}
