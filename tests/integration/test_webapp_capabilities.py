"""`GET /api/capabilities`, validated against the schema the front-end binds to.

The schema is the contract (`webapp/schemas/capabilities.json`); the endpoint is
one implementation of it. Validating the live response here is what stops the
two drifting, and it is the reason `jsonschema` is a test dependency rather than
a runtime one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from core.config import Settings

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "webapp" / "schemas" / "capabilities.json"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def test_local_mode_reports_no_account_service(api_client: TestClient, validator) -> None:
    capabilities = api_client.get("/api/capabilities").json()

    validator.validate(capabilities)
    assert capabilities["mode"] == "local"
    assert capabilities["auth"] is False
    assert capabilities["auth_methods"] == []
    assert capabilities["accounts_base"] is None
    assert capabilities["history"] == "local"


def test_local_mode_can_always_write_profiles(api_client: TestClient) -> None:
    """No account exists to sign in to, so write authority cannot depend on one."""
    assert api_client.get("/api/capabilities").json()["profile_write"] is True


def test_hosted_mode_reports_the_account_service(hosted_client: TestClient, validator) -> None:
    capabilities = hosted_client.get("/api/capabilities").json()

    validator.validate(capabilities)
    assert capabilities["mode"] == "hosted"
    assert capabilities["auth"] is True
    assert capabilities["accounts"] is True
    assert capabilities["auth_methods"] == ["password"]
    assert capabilities["accounts_base"] == "/accounts"
    assert capabilities["history"] == "server"


def test_hosted_profile_write_follows_the_caller_not_the_deployment(
    hosted_client: TestClient, signed_in_headers: dict[str, str], validator
) -> None:
    anonymous = hosted_client.get("/api/capabilities").json()
    signed_in = hosted_client.get("/api/capabilities", headers=signed_in_headers).json()

    validator.validate(anonymous)
    validator.validate(signed_in)
    assert anonymous["profile_write"] is False
    assert signed_in["profile_write"] is True


def test_an_unverifiable_token_is_treated_as_anonymous(hosted_client: TestClient) -> None:
    response = hosted_client.get("/api/capabilities", headers={"Authorization": "Bearer forged"})

    assert response.json()["profile_write"] is False


@pytest.mark.parametrize("client_name", ["api_client", "hosted_client"])
def test_the_default_locale_is_a_shipped_locale(request: pytest.FixtureRequest, client_name: str) -> None:
    """Not expressible in JSON Schema, so both modes assert it here."""
    capabilities = request.getfixturevalue(client_name).get("/api/capabilities").json()

    assert capabilities["default_locale"] in capabilities["locales"]


def test_configured_auth_methods_reach_the_front_end(client_factory, validator) -> None:
    """A button exists only when the backend can service the credential behind it."""
    settings = Settings.from_dict(
        {"search": {"enabled_sources": []}, "deployment": {"mode": "hosted", "auth_methods": ["password", "orcid"]}}
    )

    with client_factory(settings) as client:
        capabilities = client.get("/api/capabilities").json()

    validator.validate(capabilities)
    assert capabilities["auth_methods"] == ["password", "orcid"]
