"""Repository selection helpers for local/remote profile storage."""

from __future__ import annotations

from collections.abc import Callable

import requests

from ..config import Settings
from .http_profile_repository import HttpProfileRepository, _RetryPolicy
from .profile_repository import ProfileRepository
from .yaml_profile_repository import YamlProfileRepository


def build_profile_repository(
    settings: Settings,
    *,
    headers_provider: Callable[[], dict[str, str]] | None = None,
    session: requests.Session | None = None,
) -> ProfileRepository:
    """Build the repository the settings ask for.

    ``headers_provider`` and ``session`` are ignored in local mode, so an adapter
    that builds one repository per request can pass them unconditionally. Sharing
    a session across those repositories is what keeps the upstream connection
    pool alive between requests.
    """
    repo_cfg = settings.profile_repository
    if repo_cfg.mode == "remote":
        return HttpProfileRepository(
            base_url=repo_cfg.base_url,
            timeout_seconds=repo_cfg.timeout_seconds,
            retry_policy=_RetryPolicy(
                max_attempts=repo_cfg.max_attempts,
                backoff_base_seconds=repo_cfg.backoff_base_seconds,
                backoff_max_seconds=repo_cfg.backoff_max_seconds,
            ),
            headers=dict(repo_cfg.headers),
            headers_provider=headers_provider,
            session=session,
        )
    return YamlProfileRepository()
