"""Who may mutate a profile: `mode == "local" or the request is authenticated`.

This replaces the deployment-wide read-only switch it grew out of, which had two
failure modes and no middle ground — on, and the local download could not edit
its own profiles; off, and every hosted profile was writable by anyone who found
the URL.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.factories import profile_payload

VALID_PROFILE = profile_payload(name="hydrogel", label="Hydrogel")


def _writes(client: TestClient, headers: dict[str, str] | None = None):
    return (
        client.post("/api/profiles", json=VALID_PROFILE, headers=headers),
        client.put("/api/profiles/hydrogel", json=VALID_PROFILE, headers=headers),
        client.delete("/api/profiles/hydrogel", headers=headers),
    )


def test_an_anonymous_hosted_caller_cannot_write(hosted_client: TestClient) -> None:
    for response in _writes(hosted_client):
        assert response.status_code == 401
        assert response.json() == {"error": "Sign in to manage profiles."}


def test_an_unverifiable_token_is_no_better_than_no_token(hosted_client: TestClient) -> None:
    for response in _writes(hosted_client, {"Authorization": "Bearer forged"}):
        assert response.status_code == 401


@pytest.mark.parametrize("header", ["signed-in-token", "Basic signed-in-token", "Bearer"])
def test_a_credential_that_is_not_a_bearer_token_is_ignored(hosted_client: TestClient, header: str) -> None:
    response = hosted_client.post("/api/profiles", json=VALID_PROFILE, headers={"Authorization": header})

    assert response.status_code == 401


def test_a_signed_in_hosted_caller_completes_every_verb(
    hosted_client: TestClient, signed_in_headers: dict[str, str]
) -> None:
    created, updated, deleted = _writes(hosted_client, signed_in_headers)

    assert created.status_code == 201
    assert updated.status_code == 200
    assert deleted.json() == {"deleted": "hydrogel"}


def test_an_anonymous_hosted_caller_still_reads(hosted_client: TestClient) -> None:
    """Built-ins are public. Losing that would break search for signed-out visitors."""
    assert hosted_client.get("/api/profiles").status_code == 200
    assert hosted_client.get("/api/profiles/generic").status_code == 200


def test_local_mode_needs_no_credential_at_all(api_client: TestClient) -> None:
    created, updated, deleted = _writes(api_client)

    assert created.status_code == 201
    assert updated.status_code == 200
    assert deleted.status_code == 200
