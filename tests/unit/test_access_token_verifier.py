"""Negative-path tests for the webapp's local access-token verification.

Every case here is an attacker's first attempt, so each one is written as "this
token must not be accepted" rather than "the library handles it". Signing keys
are generated per test; nothing is checked in.
"""

from __future__ import annotations

import json
import time

import jwt
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

from tests.support.http_doubles import FakeResponse, RaisingSession, ScriptedSession
from webapp.auth import AccessTokenVerifier

ISSUER = "https://bierre.ca/accounts"
AUDIENCE = "bierre-api"
JWKS_URL = "https://bierre.ca/accounts/.well-known/jwks.json"
CURRENT_KID = "2026-08-current"
NEXT_KID = "2026-08-next"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _keypair(kid: str) -> tuple[Ed25519PrivateKey, dict]:
    private_key = Ed25519PrivateKey.generate()
    jwk = json.loads(OKPAlgorithm.to_jwk(private_key.public_key()))
    return private_key, {**jwk, "kid": kid, "use": "sig", "alg": "EdDSA"}


def _token(private_key: Ed25519PrivateKey, kid: str, **overrides) -> str:
    issued_at = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "0198c8d5-6f4a-7c3b-9d21-4f6a8b0c1d2e",
        "jti": "0198c8d5-7a11-7f04-8c66-2b9d5e0417aa",
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + 900,
        "typ": "access",
        "sv": 1,
        "ev": False,
        **overrides,
    }
    return jwt.encode(claims, private_key, algorithm="EdDSA", headers={"kid": kid})


def _jwks_response(*jwks: dict) -> FakeResponse:
    return FakeResponse(json_data={"keys": list(jwks)})


@pytest.fixture
def current_key() -> tuple[Ed25519PrivateKey, dict]:
    return _keypair(CURRENT_KID)


@pytest.fixture
def next_key() -> tuple[Ed25519PrivateKey, dict]:
    return _keypair(NEXT_KID)


@pytest.fixture
def clock() -> Clock:
    return Clock()


def _verifier(session, clock: Clock) -> AccessTokenVerifier:
    return AccessTokenVerifier(
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
        session=session,
        clock=clock,
    )


# --- the happy path ----------------------------------------------------------


def test_a_current_token_verifies_and_returns_its_claims(current_key, next_key, clock) -> None:
    private_key, jwk = current_key
    session = ScriptedSession([_jwks_response(jwk, next_key[1])])

    claims = _verifier(session, clock).verify(_token(private_key, CURRENT_KID))

    assert claims is not None
    assert claims["sub"] == "0198c8d5-6f4a-7c3b-9d21-4f6a8b0c1d2e"
    assert claims["typ"] == "access"


def test_the_next_key_verifies_too_so_rotation_needs_no_downtime(current_key, next_key, clock) -> None:
    """`next` only verifies; a token it signed is what a just-rotated service issues."""
    session = ScriptedSession([_jwks_response(current_key[1], next_key[1])])

    assert _verifier(session, clock).verify(_token(next_key[0], NEXT_KID)) is not None


# --- forgery -----------------------------------------------------------------


def test_alg_none_is_rejected(current_key, clock) -> None:
    session = ScriptedSession([_jwks_response(current_key[1])])
    unsigned = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "jti": "1", "iat": 0, "nbf": 0, "exp": 9999999999, "typ": "access"},
        key=None,
        algorithm="none",
        headers={"kid": CURRENT_KID},
    )

    assert _verifier(session, clock).verify(unsigned) is None


def test_hmac_signed_with_the_published_public_key_is_rejected(current_key, clock) -> None:
    """Algorithm confusion: the public key is public, so it must never be a shared secret."""
    session = ScriptedSession([_jwks_response(current_key[1])])
    forged = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "jti": "1", "iat": 0, "nbf": 0, "exp": 9999999999, "typ": "access"},
        key=current_key[1]["x"],
        algorithm="HS256",
        headers={"kid": CURRENT_KID},
    )

    assert _verifier(session, clock).verify(forged) is None


def test_a_token_signed_by_an_unpublished_key_is_rejected(current_key, clock) -> None:
    attacker_key, _ = _keypair(CURRENT_KID)
    session = ScriptedSession([_jwks_response(current_key[1])])

    assert _verifier(session, clock).verify(_token(attacker_key, CURRENT_KID)) is None


@pytest.mark.parametrize("kid", ["unknown-kid", ""])
def test_a_token_whose_kid_is_not_published_is_rejected(current_key, clock, kid: str) -> None:
    """No fallback: trying every key in turn is how a retired key stays usable."""
    session = ScriptedSession([_jwks_response(current_key[1])])

    assert _verifier(session, clock).verify(_token(current_key[0], kid)) is None


def test_a_token_that_is_not_a_token_is_rejected(current_key, clock) -> None:
    session = ScriptedSession([_jwks_response(current_key[1])])

    assert _verifier(session, clock).verify("not-a-jwt") is None


# --- claims ------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"exp": int(time.time()) - 3600}, id="expired"),
        pytest.param({"iss": "https://evil.example/accounts"}, id="wrong issuer"),
        pytest.param({"aud": "bierre-digest"}, id="wrong audience"),
        pytest.param({"typ": "refresh"}, id="refresh artefact presented as a bearer token"),
    ],
)
def test_claims_that_do_not_match_the_contract_are_rejected(current_key, clock, overrides: dict) -> None:
    session = ScriptedSession([_jwks_response(current_key[1])])

    assert _verifier(session, clock).verify(_token(current_key[0], CURRENT_KID, **overrides)) is None


@pytest.mark.parametrize("claim", ["exp", "iat", "nbf", "iss", "aud", "sub", "jti"])
def test_a_missing_registered_claim_is_rejected(current_key, clock, claim: str) -> None:
    session = ScriptedSession([_jwks_response(current_key[1])])
    private_key, jwk = current_key
    token = _token(private_key, CURRENT_KID)
    claims = jwt.decode(token, key=jwt.PyJWK(jwk).key, algorithms=["EdDSA"], audience=AUDIENCE, issuer=ISSUER)
    del claims[claim]
    incomplete = jwt.encode(claims, private_key, algorithm="EdDSA", headers={"kid": CURRENT_KID})

    assert _verifier(session, clock).verify(incomplete) is None


# --- the JWKS cache ----------------------------------------------------------


def test_keys_are_fetched_once_per_ttl(current_key, clock) -> None:
    session = ScriptedSession([_jwks_response(current_key[1]), _jwks_response(current_key[1])])
    verifier = _verifier(session, clock)
    token = _token(current_key[0], CURRENT_KID)

    verifier.verify(token)
    clock.now += 599
    verifier.verify(token)
    assert session.call_count == 1

    clock.now += 1
    verifier.verify(token)
    assert session.call_count == 2


def test_an_unreachable_jwks_keeps_the_keys_already_held(current_key, clock) -> None:
    """A blip at the account service must not sign every open tab out."""
    verifier = _verifier(ScriptedSession([_jwks_response(current_key[1])]), clock)
    token = _token(current_key[0], CURRENT_KID)
    verifier.verify(token)

    verifier._session = RaisingSession(requests.ConnectionError("boom"))
    clock.now += 601

    assert verifier.verify(token) is not None


def test_a_verifier_that_never_reached_the_jwks_accepts_nothing(current_key, clock) -> None:
    verifier = _verifier(RaisingSession(requests.ConnectionError("boom")), clock)

    assert verifier.verify(_token(current_key[0], CURRENT_KID)) is None


def test_an_unusable_key_in_the_jwks_does_not_take_the_usable_ones_with_it(current_key, clock) -> None:
    broken = {"kid": "broken", "kty": "OKP", "crv": "P-42", "x": "nope", "use": "sig", "alg": "EdDSA"}
    session = ScriptedSession([_jwks_response(broken, current_key[1])])

    assert _verifier(session, clock).verify(_token(current_key[0], CURRENT_KID)) is not None
