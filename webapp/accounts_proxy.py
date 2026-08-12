"""Same-origin proxy from the webapp to ``bierre-ca``.

The browser must see one origin: the refresh cookie is scoped to
``/accounts/api/auth`` and ``SameSite=Lax``, so a cross-origin account service
would simply not receive it. Everything under the accounts prefix is therefore
forwarded verbatim — credentials in (``Authorization``, ``Cookie``,
``X-CSRF-Token``), credentials out (every ``Set-Cookie``), status and error body
untouched, because ``bierre-ca`` owns those decisions and this hop must not
reinterpret them.

Header handling is allow-list based in both directions. Hop-by-hop headers
(``Connection``, ``Transfer-Encoding``, …) describe *this* connection and must
not be copied onto the next one, and ``Content-Encoding``/``Content-Length``
would describe a body that has already been decoded by the time it is relayed.

In production nginx routes ``/accounts/`` straight to ``bierre-ca`` and this
router never sees a request. It exists so a hosted stack behind any other front
door — or none at all — still works.
"""

from __future__ import annotations

import logging

import requests
from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger("bierre.webapp.accounts")

PROXY_TIMEOUT_SECONDS = 20
PROXY_METHODS = ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS", "HEAD"]

FORWARDED_REQUEST_HEADERS = (
    "authorization",
    "cookie",
    "x-csrf-token",
    "content-type",
    "accept",
    "accept-language",
    "user-agent",
)
FORWARDED_RESPONSE_HEADERS = (
    "content-type",
    "cache-control",
    "location",
    "retry-after",
    "vary",
    "www-authenticate",
)


def create_accounts_proxy_router(*, prefix: str, upstream_base_url: str, session: requests.Session) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["accounts"])
    base_url = upstream_base_url.rstrip("/")

    @router.api_route("/{upstream_path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy(upstream_path: str, request: Request) -> Response:
        body = await request.body()
        return await run_in_threadpool(_forward, session, base_url, prefix, upstream_path, request, body)

    return router


def _forward(
    session: requests.Session,
    base_url: str,
    prefix: str,
    upstream_path: str,
    request: Request,
    body: bytes,
) -> Response:
    url = f"{base_url}{prefix}/{upstream_path}"
    try:
        upstream = session.request(
            method=request.method,
            url=url,
            params=request.url.query,
            data=body or None,
            headers=_request_headers(request),
            timeout=PROXY_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        logger.error("Cannot reach the account service at %s: %s", url, exc)
        return Response(
            content=b'{"error":"The account service is unavailable."}',
            status_code=502,
            media_type="application/json",
        )
    return _relay(upstream)


def _request_headers(request: Request) -> dict[str, str]:
    headers = {
        name: value for name in FORWARDED_REQUEST_HEADERS if (value := request.headers.get(name)) is not None
    }
    client_host = request.client.host if request.client else ""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for or client_host:
        headers["X-Forwarded-For"] = forwarded_for or client_host
    headers["X-Forwarded-Proto"] = request.headers.get("x-forwarded-proto") or request.url.scheme
    headers["X-Forwarded-Host"] = request.headers.get("x-forwarded-host") or request.url.netloc
    return headers


def _relay(upstream: requests.Response) -> Response:
    response = Response(content=upstream.content, status_code=upstream.status_code)
    for name in FORWARDED_RESPONSE_HEADERS:
        value = upstream.headers.get(name)
        if value:
            response.headers[name] = value
    for cookie in _set_cookie_headers(upstream):
        response.headers.append("set-cookie", cookie)
    return response


def _set_cookie_headers(upstream: requests.Response) -> list[str]:
    """Every ``Set-Cookie`` line, not the comma-joined one.

    Login sends two cookies in two headers; ``requests`` folds repeated headers
    into one comma-separated string, and splitting that back apart breaks on the
    commas inside cookie ``Expires`` dates. The underlying urllib3 response keeps
    them apart, so read them from there.
    """
    raw_headers = getattr(upstream.raw, "headers", None)
    if hasattr(raw_headers, "getlist"):
        return list(raw_headers.getlist("Set-Cookie"))
    value = upstream.headers.get("set-cookie")
    return [value] if value else []
