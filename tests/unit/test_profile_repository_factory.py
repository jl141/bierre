"""Unit tests for `core.repositories.factory.build_profile_repository`."""

from __future__ import annotations

import pytest
import requests

from core.config import Settings
from core.repositories.factory import build_profile_repository
from core.repositories.http_profile_repository import HttpProfileRepository
from core.repositories.yaml_profile_repository import YamlProfileRepository


def test_local_mode_returns_the_yaml_repository() -> None:
    repository = build_profile_repository(Settings.from_dict({"profile_repository": {"mode": "local"}}))

    assert isinstance(repository, YamlProfileRepository)


def test_an_unknown_mode_falls_back_to_local_storage() -> None:
    repository = build_profile_repository(Settings.from_dict({"profile_repository": {"mode": "wat"}}))

    assert isinstance(repository, YamlProfileRepository)


def test_remote_mode_returns_a_configured_http_repository() -> None:
    settings = Settings.from_dict(
        {
            "profile_repository": {
                "mode": "remote",
                "base_url": "https://example.org/",
                "timeout_seconds": 11,
                "max_attempts": 4,
                "backoff_base_seconds": 0.25,
                "backoff_max_seconds": 2.0,
                "headers": {"Authorization": "Bearer token"},
            }
        }
    )

    repository = build_profile_repository(settings)

    assert isinstance(repository, HttpProfileRepository)
    assert repository._base_url == "https://example.org"  # trailing slash normalised
    assert repository._timeout_seconds == 11
    assert repository._retry_policy.max_attempts == 4
    assert repository._headers == {"Authorization": "Bearer token"}


def test_remote_mode_without_a_base_url_fails_loudly() -> None:
    settings = Settings.from_dict({"profile_repository": {"mode": "remote", "base_url": ""}})

    with pytest.raises(ValueError, match="base_url is required"):
        build_profile_repository(settings)


def test_a_remote_repository_carries_the_per_request_seams() -> None:
    """The webapp builds one of these per request; both seams have to survive."""
    settings = Settings.from_dict({"profile_repository": {"mode": "remote", "base_url": "https://example.org"}})
    session = requests.Session()

    repository = build_profile_repository(
        settings, headers_provider=lambda: {"Authorization": "Bearer caller"}, session=session
    )

    assert repository._session is session
    assert repository._headers_provider() == {"Authorization": "Bearer caller"}


def test_local_mode_ignores_the_remote_only_arguments() -> None:
    """An adapter can pass them unconditionally instead of branching on the mode."""
    repository = build_profile_repository(
        Settings(), headers_provider=lambda: {"Authorization": "Bearer caller"}, session=requests.Session()
    )

    assert isinstance(repository, YamlProfileRepository)
