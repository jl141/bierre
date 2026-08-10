"""Unit tests for `core.repositories.factory.build_profile_repository`."""

from __future__ import annotations

import pytest

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
