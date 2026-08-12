"""The three real paths that exist because a link is not a hash route."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

REAL_PATHS = ["/auth/callback", "/accounts/verify", "/unsubscribe"]


@pytest.mark.parametrize("path", REAL_PATHS)
@pytest.mark.parametrize("client_name", ["api_client", "hosted_client"])
def test_each_real_path_serves_a_document_in_both_modes(
    request: pytest.FixtureRequest, client_name: str, path: str
) -> None:
    response = request.getfixturevalue(client_name).get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<h1>" in response.text


@pytest.mark.parametrize("path", REAL_PATHS)
def test_a_one_time_token_in_the_link_is_never_echoed(api_client: TestClient, path: str) -> None:
    """These URLs carry credentials; rendering one back is an injection sink."""
    response = api_client.get(path, params={"token": "s3cret-token"})

    assert "s3cret-token" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_the_verify_page_is_served_here_not_forwarded_to_the_account_service(hosted_client: TestClient) -> None:
    """It sits under the proxied prefix, so route order is what keeps it local."""
    response = hosted_client.get("/accounts/verify")

    assert response.status_code == 200
    assert "Email verification" in response.text
