"""The `/accounts` proxy, against a real socket.

One origin is not cosmetic: the refresh cookie is `SameSite=Lax` and scoped to
`/accounts/api/auth`, so a browser talking to the account service on another
origin would simply never send it. These tests assert the two directions that
make that work — credentials in, cookies out — plus the rule that this hop
decides nothing: whatever status and body bierre-ca produced is what the caller
sees.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.support.accounts_api import accounts_api_server


@pytest.fixture
def proxy(client_factory, hosted_settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list[dict]]]:
    with accounts_api_server() as (base_url, received):
        monkeypatch.setenv("BIERRE_CA_BASE_URL", base_url)
        with client_factory(hosted_settings) as client:
            yield client, received


def test_the_caller_credentials_are_forwarded_verbatim(proxy) -> None:
    client, received = proxy

    client.post(
        "/accounts/api/auth/refresh",
        headers={"Authorization": "Bearer abc.def.ghi", "Cookie": "bierre_refresh=opaque", "X-CSRF-Token": "csrf-1"},
    )

    assert received[-1]["headers"]["authorization"] == "Bearer abc.def.ghi"
    assert received[-1]["headers"]["cookie"] == "bierre_refresh=opaque"
    assert received[-1]["headers"]["x-csrf-token"] == "csrf-1"


def test_both_session_cookies_survive_as_separate_headers(proxy) -> None:
    """Folding them into one comma-joined header loses one of the two cookies."""
    client, _ = proxy

    response = client.post("/accounts/api/auth/login", json={"email": "a@example.org", "password": "x" * 12})

    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert any(cookie.startswith("bierre_refresh=") and "HttpOnly" in cookie for cookie in cookies)
    assert any(cookie.startswith("bierre_csrf=") for cookie in cookies)


def test_method_path_query_and_body_reach_the_account_service(proxy) -> None:
    client, received = proxy

    client.patch("/accounts/api/auth/me", params={"format": "json"}, json={"display_name": "Ada"})

    assert received[-1]["method"] == "PATCH"
    assert received[-1]["path"] == "/accounts/api/auth/me"
    assert received[-1]["query"] == "format=json"
    assert received[-1]["body"] == '{"display_name":"Ada"}'


def test_a_repeated_query_parameter_arrives_repeated(proxy) -> None:
    """Collapsing the query into a dict would silently drop all but one value."""
    client, received = proxy

    client.get("/accounts/api/profiles?tag=a&tag=b")

    assert received[-1]["query"] == "tag=a&tag=b"


def test_the_original_client_is_named_in_x_forwarded_for(proxy) -> None:
    """bierre-ca rate-limits per IP, and every hop would otherwise be this proxy."""
    client, received = proxy

    client.get("/accounts/api/profiles")

    assert received[-1]["headers"]["x-forwarded-for"]
    assert received[-1]["headers"]["x-forwarded-proto"] == "http"


def test_an_upstream_rejection_is_relayed_untouched(proxy) -> None:
    client, _ = proxy

    response = client.get("/accounts/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"error": "Sign in first."}


def test_a_rate_limit_keeps_its_retry_after(proxy) -> None:
    """`HttpProfileRepository` retries a 429, so the header it retries on must arrive."""
    client, _ = proxy

    response = client.post("/accounts/api/auth/refresh")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"


def test_a_bodyless_success_stays_bodyless(proxy) -> None:
    client, _ = proxy

    response = client.post("/accounts/api/auth/logout")

    assert response.status_code == 204
    assert response.content == b""


def test_an_unreachable_account_service_is_a_502(client_factory, hosted_settings, monkeypatch) -> None:
    with accounts_api_server() as (base_url, _):
        monkeypatch.setenv("BIERRE_CA_BASE_URL", base_url)
    with client_factory(hosted_settings) as client:
        response = client.get("/accounts/api/auth/me")

    assert response.status_code == 502
    assert response.json() == {"error": "The account service is unavailable."}


def test_local_mode_has_no_proxy_at_all(api_client: TestClient) -> None:
    """The download must not hold a route that would reach for the network."""
    assert api_client.get("/accounts/api/auth/me").status_code == 404


def test_local_mode_builds_no_upstream_client(api_client: TestClient) -> None:
    assert api_client.app.state.upstream_session is None
    assert api_client.app.state.token_verifier is None


def test_hosted_mode_verifies_against_the_account_services_own_jwks(hosted_settings, monkeypatch) -> None:
    from webapp import server

    monkeypatch.setenv("BIERRE_CA_BASE_URL", "http://bierre-ca:8000/")
    app = server.create_app(hosted_settings)

    assert app.state.token_verifier._jwks_url == "http://bierre-ca:8000/accounts/.well-known/jwks.json"
    app.state.upstream_session.close()
