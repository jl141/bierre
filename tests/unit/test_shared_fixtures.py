"""The `bierre` half of the WS-0 contract check.

The mirror of this file is `bierre-ca/tests/test_shared_fixtures.py`, which asserts
the same payloads against the service that produces them. Here they are asserted
against the client that consumes them, so a wire change breaks whichever repo
forgot to update the fixtures.
"""

from __future__ import annotations

import base64
import json

import pytest

from core.repositories.http_profile_repository import HttpProfileRepository
from core.repositories.profile_repository import DomainProfile, ProfileNotFoundError
from tests.support.fixtures import (
    digest_of,
    fixture_bytes,
    fixture_names,
    load_fixture,
    manifest,
)
from tests.support.http_doubles import FakeResponse, ScriptedSession


def _repo(session: ScriptedSession) -> HttpProfileRepository:
    return HttpProfileRepository(base_url="https://bierre.ca/accounts", session=session)


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def test_the_manifest_covers_every_fixture() -> None:
    assert sorted(manifest()) == fixture_names()


@pytest.mark.parametrize("filename", fixture_names())
def test_fixture_bytes_match_the_manifest(filename: str) -> None:
    """Byte drift between the two repos shows up here, in the repo that drifted."""
    assert digest_of(filename) == manifest()[filename]


@pytest.mark.parametrize("name", ["login", "me", "profiles_list", "profile_get", "error"])
def test_fixtures_are_utf8_json_objects_ending_in_a_newline(name: str) -> None:
    raw = fixture_bytes(name)

    assert raw.endswith(b"\n")
    assert isinstance(json.loads(raw.decode("utf-8")), dict)


def test_login_carries_the_same_user_object_as_me() -> None:
    assert load_fixture("login")["user"] == load_fixture("me")


def test_the_access_token_is_a_short_lived_access_jwt() -> None:
    login = load_fixture("login")
    claims = json.loads(_b64url_decode(login["access_token"].split(".")[1]))

    assert claims["typ"] == "access"
    assert claims["iss"] == "https://bierre.ca/accounts"
    assert claims["aud"] == "bierre-api"
    assert claims["exp"] - claims["iat"] == login["expires_in"] == 900


def test_the_list_response_parses_into_profile_summaries() -> None:
    session = ScriptedSession([FakeResponse(json_data=load_fixture("profiles_list"))])

    listed = _repo(session).list_profiles()

    assert [item.profile_id for item in listed] == [
        "generic",
        "antimicrobial-review",
        "antimicrobial-review-2",
    ]
    assert [item.is_builtin for item in listed] == [True, False, False]
    assert session.calls[0]["url"] == "https://bierre.ca/accounts/api/profiles"


def test_the_get_response_unwraps_into_a_domain_profile() -> None:
    fixture = load_fixture("profile_get")
    session = ScriptedSession([FakeResponse(json_data=fixture)])

    payload = _repo(session).get_profile("antimicrobial-review")

    assert payload == fixture["profile"]
    assert DomainProfile.from_dict(payload).name == fixture["id"]


def test_the_fallback_bucket_is_last() -> None:
    buckets = load_fixture("profile_get")["profile"]["buckets"]

    assert [bucket["fallback"] for bucket in buckets] == [False, True]


def test_the_error_body_is_the_message_the_client_raises() -> None:
    session = ScriptedSession([FakeResponse(status_code=404, json_data=load_fixture("error"))])

    with pytest.raises(ProfileNotFoundError, match="Invalid email or password."):
        _repo(session).get_profile("antimicrobial-review")
