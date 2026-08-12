"""Hosted profile writes, carried to the profile service as the caller.

The failure this guards against is subtle and total: a repository built once at
start-up would send the same credential for everyone, so bierre-ca would resolve
ownership against the service account instead of the person, and every user
would be looking at the same profiles.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from core.config import Settings
from tests.factories import profile_payload
from tests.support.profile_api import profile_api_server

VALID_PROFILE = profile_payload(name="hydrogel", label="Hydrogel")


@pytest.fixture
def remote_client(client_factory) -> Iterator[tuple[TestClient, list[dict]]]:
    with profile_api_server() as (base_url, received):
        settings = Settings.from_dict(
            {
                "search": {"enabled_sources": []},
                "deployment": {"mode": "hosted"},
                "profile_repository": {"mode": "remote", "base_url": base_url, "max_attempts": 1},
            }
        )
        with client_factory(settings) as client:
            yield client, received


def test_a_signed_in_write_reaches_the_profile_service_as_that_caller(
    remote_client, signed_in_headers: dict[str, str]
) -> None:
    client, received = remote_client

    response = client.post(
        "/api/profiles",
        json=VALID_PROFILE,
        headers={**signed_in_headers, "Cookie": "bierre_refresh=opaque", "X-CSRF-Token": "csrf-1"},
    )

    assert response.status_code == 201
    assert received[-1]["method"] == "POST"
    assert received[-1]["headers"]["authorization"] == signed_in_headers["Authorization"]
    assert received[-1]["headers"]["cookie"] == "bierre_refresh=opaque"
    assert received[-1]["headers"]["x-csrf-token"] == "csrf-1"


def test_two_callers_do_not_share_a_credential(remote_client, signed_in_headers: dict[str, str]) -> None:
    client, received = remote_client

    client.get("/api/profiles", headers=signed_in_headers)
    client.get("/api/profiles")

    assert received[-2]["headers"]["authorization"] == signed_in_headers["Authorization"]
    assert received[-1]["headers"]["authorization"] is None


def test_an_anonymous_write_never_leaves_this_process(remote_client) -> None:
    client, received = remote_client

    response = client.post("/api/profiles", json=VALID_PROFILE)

    assert response.status_code == 401
    assert received == []


def test_a_run_loads_its_profile_with_the_callers_credentials(
    remote_client, signed_in_headers: dict[str, str]
) -> None:
    """A hosted run may name a profile only its owner can read."""
    client, received = remote_client

    client.post("/api/run", json={"question": "q", "profile_id": "generic"}, headers=signed_in_headers)

    profile_reads = [item for item in received if item["path"] == "/api/profiles/generic"]
    assert profile_reads
    assert all(item["headers"]["authorization"] == signed_in_headers["Authorization"] for item in profile_reads)
