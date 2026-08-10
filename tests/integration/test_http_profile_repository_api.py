"""`HttpProfileRepository` against a real loopback HTTP server.

The unit tests stub the transport; this one keeps real sockets, real `requests`
and real JSON in the loop, so a change in how the repository builds URLs or
bodies is caught.
"""

from __future__ import annotations

import pytest

from core.repositories.http_profile_repository import HttpProfileRepository, _RetryPolicy
from core.repositories.profile_repository import (
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileStoreError,
    ProtectedProfileError,
)
from tests.support.profile_api import profile_api_server


@pytest.fixture
def remote_repo():
    with profile_api_server() as base_url:
        yield HttpProfileRepository(base_url=base_url, timeout_seconds=3)


def test_full_crud_flow_over_http(remote_repo: HttpProfileRepository) -> None:
    created = remote_repo.create_profile({"label": "Hydrogel Search", "default_question": "q1"})
    profile_id = created["id"]

    assert profile_id == "hydrogel-search"
    assert any(item.profile_id == profile_id for item in remote_repo.list_profiles())
    assert remote_repo.get_profile(profile_id)["label"] == "Hydrogel Search"

    updated = remote_repo.update_profile(profile_id, {"default_question": "q2"})
    assert updated["profile"]["default_question"] == "q2"

    remote_repo.delete_profile(profile_id)
    with pytest.raises(ProfileNotFoundError):
        remote_repo.get_profile(profile_id)


def test_listing_reports_built_in_flags_from_the_server(remote_repo: HttpProfileRepository) -> None:
    summaries = {item.profile_id: item for item in remote_repo.list_profiles()}

    assert summaries["generic"].is_builtin is True
    assert summaries["generic"].created_at


def test_server_side_conflicts_and_protections_map_to_domain_errors(remote_repo: HttpProfileRepository) -> None:
    with pytest.raises(ProfileConflictError):
        remote_repo.create_profile({"label": "generic"})

    with pytest.raises(ProtectedProfileError):
        remote_repo.delete_profile("generic")


def test_an_unreachable_server_raises_a_store_error() -> None:
    with profile_api_server() as base_url:
        dead_url = base_url
    repo = HttpProfileRepository(
        base_url=dead_url, timeout_seconds=1, retry_policy=_RetryPolicy(max_attempts=1)
    )

    with pytest.raises(ProfileStoreError, match="request failed"):
        repo.list_profiles()


def test_two_servers_do_not_share_state() -> None:
    with profile_api_server() as first_url, profile_api_server() as second_url:
        HttpProfileRepository(base_url=first_url).create_profile({"label": "only-here"})

        second = HttpProfileRepository(base_url=second_url)

        assert [item.profile_id for item in second.list_profiles()] == ["generic"]
