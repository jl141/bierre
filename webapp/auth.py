"""Local verification of bierre-ca access tokens.

This is a *UI* decision only. It answers one question — is the caller signed in,
and as whom — so the webapp knows whether a profile write is allowed to leave
the building at all. ``bierre-ca`` re-verifies every forwarded call and stays the
sole authority on ownership; nothing here may be treated as an authorisation.

Verification follows ``PRD-USER-ACCOUNTS.md`` §5.2 exactly: EdDSA as a
one-element allow-list, every registered claim required, issuer and audience
checked, and ``typ == "access"`` so a refresh artefact can never authenticate a
request.

Keys are cached for ten minutes and refreshed only on expiry. An unknown ``kid``
inside a fresh cache is rejected outright rather than triggering a fetch: the
JWKS always publishes the next key alongside the current one, so a rotation is
already covered, and a fetch-on-unknown-kid path would let anyone drive
outbound requests by presenting garbage.

Imported only in hosted mode. PyJWT and its crypto stack are needed nowhere else,
and the local download must keep working without them.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import jwt
import requests

logger = logging.getLogger("bierre.webapp.auth")

ALGORITHMS = ["EdDSA"]
REQUIRED_CLAIMS = ["exp", "iat", "nbf", "iss", "aud", "sub", "jti"]
LEEWAY_SECONDS = 60
JWKS_CACHE_TTL_SECONDS = 600
JWKS_TIMEOUT_SECONDS = 5


class AccessTokenVerifier:
    """Verifies access tokens against a cached JWKS document."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        session: requests.Session | None = None,
        cache_ttl_seconds: int = JWKS_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._session = session or requests.Session()
        self._cache_ttl_seconds = cache_ttl_seconds
        self._clock = clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None

    def verify(self, token: str) -> dict[str, Any] | None:
        """Return the claims of a valid access token, or None for anything else."""
        key = self._key_for(self._kid_of(token))
        if key is None:
            return None
        try:
            claims = jwt.decode(
                token,
                key=key.key,
                algorithms=ALGORITHMS,
                issuer=self._issuer,
                audience=self._audience,
                leeway=LEEWAY_SECONDS,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.PyJWTError as exc:
            logger.debug("Rejected access token: %s", exc)
            return None
        if claims.get("typ") != "access":
            logger.debug("Rejected access token: typ is %r, not 'access'", claims.get("typ"))
            return None
        return claims

    @staticmethod
    def _kid_of(token: str) -> str:
        try:
            return str(jwt.get_unverified_header(token).get("kid") or "")
        except jwt.PyJWTError:
            return ""

    def _key_for(self, kid: str) -> jwt.PyJWK | None:
        if not kid:
            return None
        if self._is_stale():
            self._refresh_keys()
        return self._keys.get(kid)

    def _is_stale(self) -> bool:
        return self._fetched_at is None or self._clock() - self._fetched_at >= self._cache_ttl_seconds

    def _refresh_keys(self) -> None:
        """Reload the JWKS, keeping the previous keys if the fetch fails.

        A momentarily unreachable account service must not sign every user out of
        the UI; the tokens themselves are still valid and bierre-ca still accepts
        them.
        """
        try:
            response = self._session.get(self._jwks_url, timeout=JWKS_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Could not refresh JWKS from %s: %s", self._jwks_url, exc)
            return

        keys = _parse_jwks(payload)
        if not keys:
            logger.warning("JWKS at %s carried no usable keys", self._jwks_url)
            return
        self._keys = keys
        self._fetched_at = self._clock()


def _parse_jwks(payload: Any) -> dict[str, jwt.PyJWK]:
    entries = payload.get("keys") if isinstance(payload, dict) else None
    keys: dict[str, jwt.PyJWK] = {}
    for entry in entries or []:
        kid = str(entry.get("kid") or "") if isinstance(entry, dict) else ""
        if not kid:
            continue
        try:
            keys[kid] = jwt.PyJWK(entry)
        except jwt.PyJWTError as exc:
            logger.warning("Skipping unusable JWK %r: %s", kid, exc)
    return keys
