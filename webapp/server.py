#!/usr/bin/env python3
"""FastAPI adapter that serves the bierre UI and drives the core pipeline.

    python webapp/server.py
    open http://127.0.0.1:8765

The ASGI app is also importable for a production server:

    uvicorn webapp.server:app          # honours $BIERRE_CONFIG

Scope: this adapter is a thin transport in front of ``core``. Accounts,
profile ownership and search history live in bierre-ca.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import sys
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import requests
import uvicorn
from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Path as PathParam, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import sentry_sdk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import (  # noqa: E402
    ProfileService,
    RunSearchRequest,
    SearchService,
    Settings,
    build_profile_repository,
)
from core.repositories.profile_repository import (  # noqa: E402
    DomainProfile,
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileRepository,
    ProfileStoreError,
    ProfileValidationError,
    ProtectedProfileError,
)
from webapp import pages  # noqa: E402
from webapp.accounts_proxy import create_accounts_proxy_router  # noqa: E402
from webapp.capabilities import build_capabilities  # noqa: E402

if TYPE_CHECKING:
    from webapp.auth import AccessTokenVerifier

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Same grammar the YAML repository enforces on filenames. Validating here keeps
# path traversal from ever reaching the storage layer, regardless of backend.
PROFILE_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

MAX_QUESTION_LENGTH = 1000
MAX_PROFILE_ID_LENGTH = 96
MAX_REQUEST_BYTES = 1024 * 1024
# A run that serialises past this is still returned, but it means the UI is
# about to stall on a multi-megabyte table — worth a line in the terminal.
RESULT_WARN_BYTES = 4 * 1024 * 1024

BIERRE_CA_TIMEOUT_SECONDS = 75
BIERRE_CA_DEFAULT_BASE_URL = "https://bierre.ca/accounts"

# Credentials the caller presented, replayed to bierre-ca so it authorises the
# end user rather than this service.
FORWARDED_AUTH_HEADERS = ("authorization", "cookie", "x-csrf-token")

logger = logging.getLogger("bierre.webapp")

ProfileId = Annotated[
    str,
    PathParam(pattern=PROFILE_ID_PATTERN, max_length=MAX_PROFILE_ID_LENGTH),
]


# --- request / response models ------------------------------------------------


class RunRequest(BaseModel):
    """Payload for ``POST /api/run``."""

    model_config = ConfigDict(extra="forbid")

    # Empty question is allowed: it falls back to the profile's default_question.
    question: str = Field(default="", max_length=MAX_QUESTION_LENGTH)
    profile_id: str = Field(pattern=PROFILE_ID_PATTERN, max_length=MAX_PROFILE_ID_LENGTH)
    offline: bool = False
    settings_overrides: dict[str, Any] = Field(default_factory=dict)
    requested_outputs: list[str] = Field(default_factory=list)
    request_id: str = Field(default="", max_length=64)


class ProfileGenerateRequest(BaseModel):
    """Payload for ``POST /bierre-ca/api/profiles/generate``."""

    model_config = ConfigDict(extra="forbid")

    research_description: str = Field(min_length=1, max_length=4000)
    label_hint: str = Field(default="", max_length=200)


class SearchSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    max_results_per_query: int
    max_queries_per_run: int
    concurrent_workers: int
    timeout_seconds: int
    enabled_sources: list[str]
    semantic_scholar_max_queries_without_key: int
    source_http_overrides: dict[str, dict[str, Any]]


class SelectionSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    top_n: int
    min_relevance: float


class ProfileRepositorySettingsOut(BaseModel):
    """Repository config minus ``headers``, which may carry credentials."""

    model_config = ConfigDict(from_attributes=True)

    mode: str
    base_url: str
    timeout_seconds: int
    max_attempts: int
    backoff_base_seconds: float
    backoff_max_seconds: float


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contact_email: str
    use_unpaywall: bool
    api_keys: dict[str, str]
    search: SearchSettingsOut
    selection: SelectionSettingsOut
    profile_repository: ProfileRepositorySettingsOut


class ProfileSummaryOut(BaseModel):
    id: str
    label: str
    created_at: str
    updated_at: str
    is_builtin: bool


class ProfileListOut(BaseModel):
    profiles: list[str]
    profiles_meta: list[ProfileSummaryOut]
    default: str


class ProfileOut(BaseModel):
    id: str
    profile: dict[str, Any]


# --- dependencies -------------------------------------------------------------


def _settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(_settings)]


def _access_claims(request: Request) -> dict[str, Any] | None:
    """Claims of the caller's access token, or None if there is no valid one.

    Local mode has no verifier and therefore no signed-in state at all; that is
    not a restriction, because local write authority does not depend on identity.
    """
    verifier = request.app.state.token_verifier
    if verifier is None:
        return None
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return verifier.verify(token)


AccessClaimsDep = Annotated["dict[str, Any] | None", Depends(_access_claims)]


def _profile_service(request: Request) -> ProfileService:
    """One service per request when the repository speaks to bierre-ca.

    A repository built once at start-up can only ever carry a fixed credential,
    which would make every hosted profile call act as the service instead of as
    the person who made it.
    """
    build_repository = request.app.state.caller_scoped_repository
    if build_repository is None:
        return request.app.state.profile_service
    return ProfileService(repository=build_repository(request))


ProfileServiceDep = Annotated[ProfileService, Depends(_profile_service)]


def _search_service(request: Request, profile_service: ProfileServiceDep) -> SearchService:
    """Load the run's profile through the caller's repository.

    A hosted run may name a profile only its owner can read, so the loader has to
    carry the same credentials as the rest of the request.
    """
    search_service = request.app.state.search_service
    if request.app.state.caller_scoped_repository is None:
        return search_service
    return replace(search_service, profile_loader=_profile_loader(profile_service))


SearchServiceDep = Annotated[SearchService, Depends(_search_service)]


def _require_writable(settings: SettingsDep, claims: AccessClaimsDep) -> None:
    """Write authority is ``mode == "local" or the request is authenticated``.

    Hosted anonymous callers are read-only. bierre-ca enforces ownership again on
    the forwarded call; this check exists so the UI gets a coherent 401 instead
    of an upstream error, never as the only thing standing between an anonymous
    caller and someone else's data.
    """
    if settings.deployment.is_hosted and claims is None:
        raise HTTPException(status_code=401, detail="Sign in to manage profiles.")


RequireWritable = Depends(_require_writable)


# --- run/search ---------------------------------------------------------------


def _ndjson(event: dict[str, Any]) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")


def _run_events(search_service: SearchService, run_request: RunSearchRequest) -> Iterator[bytes]:
    """Yield NDJSON progress events while the pipeline runs.

    The pipeline is blocking and reports progress through a callback, so it runs
    on a worker thread and hands events to this generator through a queue —
    that is what lets the client see progress before the result is ready.
    """
    events: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def on_progress(step: int, total: int, label: str) -> None:
        events.put({"type": "progress", "step": step, "total": total, "label": label})

    def worker() -> None:
        try:
            response = search_service.run(run_request, progress=on_progress)
            events.put({"type": "result", "result": response.to_dict()})
        except Exception as exc:  # reported to the UI as a stream event
            logger.exception("Run failed (request_id=%s)", run_request.request_id or "-")
            events.put({"type": "error", "error": str(exc)})
        finally:
            events.put(None)

    threading.Thread(target=worker, name="bierre-run", daemon=True).start()

    while (event := events.get()) is not None:
        line = _ndjson(event)
        if event["type"] == "result" and len(line) > RESULT_WARN_BYTES:
            logger.warning(
                "Large result payload: %.1f MiB (question=%r, profile_id=%s)",
                len(line) / (1024 * 1024),
                run_request.question[:80],
                run_request.profile_id,
            )
        yield line


def _resolve_question(payload: RunRequest, profile_service: ProfileService) -> str:
    question = payload.question.strip()
    if question:
        return question
    # Preserve the UX where an empty box runs the profile's default question.
    profile = profile_service.get_profile(payload.profile_id)
    return str(profile.get("default_question") or "").strip()


def _profile_loader(profile_service: ProfileService) -> Callable[[str], DomainProfile]:
    def load(profile_id: str) -> DomainProfile:
        payload = profile_service.get_profile(profile_id)
        return DomainProfile.from_dict({**payload, "name": profile_id})

    return load


# --- routes -------------------------------------------------------------------

api = APIRouter(prefix="/api", tags=["api"])


@api.post("/run")
def run_search(
    payload: RunRequest,
    profile_service: ProfileServiceDep,
    search_service: SearchServiceDep,
) -> StreamingResponse:
    """Stream one pipeline run as NDJSON progress/result/error events."""
    run_request = RunSearchRequest(
        question=_resolve_question(payload, profile_service),
        profile_id=payload.profile_id,
        offline=payload.offline,
        settings_overrides=payload.settings_overrides,
        requested_outputs=payload.requested_outputs,
        request_id=payload.request_id,
    )
    return StreamingResponse(
        _run_events(search_service, run_request),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


@api.get("/settings", response_model=SettingsOut)
def get_settings(settings: SettingsDep) -> Settings:
    return settings


@api.get("/capabilities")
def get_capabilities(settings: SettingsDep, claims: AccessClaimsDep) -> dict[str, Any]:
    """Describe what this deployment can do, for the front-end to gate on.

    The response shape is owned by `webapp/schemas/capabilities.json`; the test
    suite validates both modes against it rather than paying for a JSON Schema
    dependency on every request.
    """
    return build_capabilities(settings, authenticated=claims is not None)


@api.get("/profiles", response_model=ProfileListOut)
def list_profiles(settings: SettingsDep, profile_service: ProfileServiceDep) -> dict[str, Any]:
    summaries = [item.to_dict() for item in profile_service.list_profiles()]
    return {
        "profiles": [item["id"] for item in summaries],
        "profiles_meta": summaries,
        "default": settings.profile,
    }


@api.get("/profiles/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: ProfileId, profile_service: ProfileServiceDep) -> dict[str, Any]:
    return {"id": profile_id, "profile": profile_service.get_profile(profile_id)}


@api.post("/profiles", response_model=ProfileOut, status_code=201, dependencies=[RequireWritable])
def create_profile(
    profile_service: ProfileServiceDep,
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    # The repository owns the profile schema; duplicating it here would let the
    # two definitions drift apart.
    return profile_service.create_profile(payload)


@api.put("/profiles/{profile_id}", response_model=ProfileOut, dependencies=[RequireWritable])
def update_profile(
    profile_id: ProfileId,
    profile_service: ProfileServiceDep,
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    return profile_service.update_profile(profile_id, payload)


@api.delete("/profiles/{profile_id}", dependencies=[RequireWritable])
def delete_profile(profile_id: ProfileId, profile_service: ProfileServiceDep) -> dict[str, str]:
    profile_service.delete_profile(profile_id)
    return {"deleted": profile_id}


bierre_ca = APIRouter(prefix="/bierre-ca/api", tags=["bierre-ca"])


@bierre_ca.post("/profiles/generate")
def generate_profile(payload: ProfileGenerateRequest) -> StreamingResponse:
    """Proxy profile drafting to the bierre-ca service, streaming progress."""
    return StreamingResponse(
        _generate_events(payload),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


def _generate_events(payload: ProfileGenerateRequest) -> Iterator[bytes]:
    target_url = f"{_bierre_ca_base_url()}/api/profiles/generate"
    headers = {"Content-Type": "application/json"}
    api_key = (os.environ.get("BIERRE_CA_API_KEY") or "").strip()
    if api_key:
        headers["X-API-Key"] = api_key

    body: dict[str, str] = {"research_description": payload.research_description}
    if payload.label_hint:
        body["label_hint"] = payload.label_hint

    yield _ndjson({"type": "progress", "step": 1, "total": 3, "label": "Preparing prompt"})
    yield _ndjson({"type": "progress", "step": 2, "total": 3, "label": "Generating profile"})
    try:
        response = requests.post(
            target_url,
            json=body,
            headers=headers,
            timeout=BIERRE_CA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json() if response.content else {}
    except requests.HTTPError as exc:
        logger.error("bierre-ca rejected the request: %s", exc)
        yield _ndjson({"type": "error", "error": _upstream_detail(exc.response)})
        return
    except requests.RequestException as exc:
        logger.error("Cannot reach bierre-ca at %s: %s", target_url, exc)
        yield _ndjson({"type": "error", "error": f"Cannot reach bierre-ca service: {exc}"})
        return
    except ValueError as exc:
        logger.error("bierre-ca returned invalid JSON: %s", exc)
        yield _ndjson({"type": "error", "error": "bierre-ca returned a malformed response"})
        return

    yield _ndjson({"type": "progress", "step": 3, "total": 3, "label": "Applying draft"})
    yield _ndjson({"type": "result", "result": result})


def _bierre_ca_base_url() -> str:
    return os.environ.get("BIERRE_CA_BASE_URL", BIERRE_CA_DEFAULT_BASE_URL).rstrip("/")


def _upstream_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"Profile generation failed ({response.status_code})"
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error")
        if detail:
            return str(detail)
    return f"Profile generation failed ({response.status_code})"


# --- error handling -----------------------------------------------------------

# The UI reads {"error": "..."} from every failed response, so all handlers
# normalise to that shape instead of FastAPI's default {"detail": ...}.
_PROFILE_ERROR_STATUS: dict[type[ProfileStoreError], int] = {
    ProfileValidationError: 400,
    ProtectedProfileError: 403,
    ProfileNotFoundError: 404,
    ProfileConflictError: 409,
}


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        message = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'][1:]) or 'body'}: {error['msg']}"
            for error in exc.errors()
        )
        logger.warning("Rejected %s %s: %s", request.method, request.url.path, message)
        return _error_response(400, message or "Malformed request body.")

    @app.exception_handler(ProfileStoreError)
    async def _on_profile_error(request: Request, exc: ProfileStoreError) -> JSONResponse:
        status_code = _PROFILE_ERROR_STATUS.get(type(exc), 500)
        log = logger.warning if status_code < 500 else logger.error
        log("%s %s -> %s: %s", request.method, request.url.path, status_code, exc)
        return _error_response(status_code, str(exc))

    @app.exception_handler(ValueError)
    async def _on_value_error(request: Request, exc: ValueError) -> JSONResponse:
        logger.warning("Invalid request to %s %s: %s", request.method, request.url.path, exc)
        return _error_response(400, str(exc))

    # Registered on the Starlette class so mounted apps (StaticFiles) and
    # framework-raised 404/405s answer in the same shape as our own routes.
    @app.exception_handler(StarletteHTTPException)
    async def _on_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("%s %s -> %s: %s", request.method, request.url.path, exc.status_code, exc.detail)
        return _error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _on_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error_response(500, str(exc) or "Internal server error.")


# --- app ----------------------------------------------------------------------


def _forwarded_auth_headers(request: Request) -> dict[str, str]:
    return {name: value for name in FORWARDED_AUTH_HEADERS if (value := request.headers.get(name))}


def _caller_scoped_repository(
    settings: Settings, session: requests.Session
) -> Callable[[Request], ProfileRepository]:
    def build(request: Request) -> ProfileRepository:
        return build_profile_repository(
            settings,
            headers_provider=lambda: _forwarded_auth_headers(request),
            session=session,
        )

    return build


def _access_token_verifier(settings: Settings, session: requests.Session) -> "AccessTokenVerifier":
    """Build the JWKS-backed verifier.

    Imported here rather than at module scope: PyJWT and its crypto stack are a
    hosted-mode dependency, and the local download must start without them.
    """
    from webapp.auth import AccessTokenVerifier

    deployment = settings.deployment
    return AccessTokenVerifier(
        jwks_url=f"{_bierre_ca_base_url()}{deployment.jwks_path}",
        issuer=deployment.token_issuer,
        audience=deployment.token_audience,
        session=session,
    )

def init_sentry():
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        # Enable sending logs to Sentry
        enable_logs=True,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=1.0,
        # Set profile_session_sample_rate to 1.0 to profile 100%
        # of profile sessions.
        profile_session_sample_rate=1.0,
        # Set profile_lifecycle to "trace" to automatically
        # run the profiler on when there is an active transaction
        profile_lifecycle="trace",
        # To debug: set debug=True
    )

def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load(_config_path())
    hosted = settings.deployment.is_hosted
    remote_profiles = settings.profile_repository.mode == "remote"
    upstream_session = requests.Session() if hosted or remote_profiles else None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if upstream_session is not None:
                upstream_session.close()

    profile_service = ProfileService(repository=build_profile_repository(settings))

    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        # Enable sending logs to Sentry
        enable_logs=True,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=1.0,
        # Set profile_session_sample_rate to 1.0 to profile 100%
        # of profile sessions.
        profile_session_sample_rate=1.0,
        # Set profile_lifecycle to "trace" to automatically
        # run the profiler on when there is an active transaction
        profile_lifecycle="trace",
        debug=True,
        # Disable dedupe
        disabled_integrations=[sentry_sdk.integrations.dedupe.DedupeIntegration]
    )

    app = FastAPI(title="bierre web UI", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.profile_service = profile_service
    app.state.upstream_session = upstream_session
    app.state.token_verifier = _access_token_verifier(settings, upstream_session) if hosted else None
    app.state.caller_scoped_repository = (
        _caller_scoped_repository(settings, upstream_session) if remote_profiles else None
    )
    app.state.search_service = SearchService(
        base_settings=settings,
        profile_loader=_profile_loader(profile_service),
    )

    @app.get("/sentry-debug")
    async def trigger_error():
        logger.info(os.environ.get("SENTRY_DSN"))
        logger.warning("Triggering divison by zero error! (Python logger)")
        sentry_sdk.logger.warning('Triggering divison by zero error! (Sentry logger)')
        division_by_zero = 1 / 0

    @app.middleware("http")
    async def _limit_body_size(request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
            logger.warning(
                "Rejected %s %s: body of %s bytes exceeds %s",
                request.method,
                request.url.path,
                declared,
                MAX_REQUEST_BYTES,
            )
            return _error_response(413, "Request body too large.")
        return await call_next(request)

    _register_error_handlers(app)
    app.include_router(api)
    app.include_router(bierre_ca)
    # Before the proxy: /accounts/verify is a page this app renders, not a route
    # the account service knows about.
    app.include_router(pages.router)
    if hosted:
        app.include_router(
            create_accounts_proxy_router(
                prefix=settings.deployment.accounts_base,
                upstream_base_url=_bierre_ca_base_url(),
                session=upstream_session,
            )
        )
    # Mounted last so the API routes win; html=True serves index.html at "/".
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def _config_path() -> Path | None:
    raw = (os.environ.get("BIERRE_CONFIG") or "config.yaml").strip()
    return Path(raw) if raw else None


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )


app = create_app()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bierre web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", type=Path, help="Path to a settings YAML file.")
    args = parser.parse_args(argv)

    _configure_logging()
    uvicorn.run(create_app(Settings.load(args.config or _config_path())), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
