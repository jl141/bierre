"""Session-wide fixtures and safety rails.

Two rails matter here:

* `_isolate_environment` — the adapters read `BIERRE_*` environment variables at
  request time, so a developer's shell must not change test outcomes.
* `_block_external_network` — every test in this suite is meant to run offline.
  The guard turns an accidental real API call into an immediate, obvious failure
  instead of a slow, flaky one. Loopback is still allowed for the integration
  tests that run a real local HTTP server.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from core.config import Settings
from core.repositories.yaml_profile_repository import YamlProfileRepository

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_PROFILES_DIR = PROJECT_ROOT / "profiles"

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", ""}
_BIERRE_ENV_VARS = (
    "BIERRE_CONFIG",
    "BIERRE_CA_BASE_URL",
    "BIERRE_CA_API_KEY",
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Tag every test with the marker matching its directory (unit/integration/e2e).

    Lets you run one layer without decorating each test: `pytest -m unit`.
    """
    del config
    for item in items:
        parts = set(Path(str(item.fspath)).parts)
        for layer in ("unit", "integration", "e2e"):
            if layer in parts:
                item.add_marker(getattr(pytest.mark, layer))
                break


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _BIERRE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in _LOOPBACK_HOSTS:
            raise RuntimeError(
                f"Blocked outbound network call to {host!r}. Tests must stub HTTP "
                "(see tests/support/http_doubles.py) or use the loopback server."
            )
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def allow_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt out of the network guard (nothing in CI should need this)."""
    monkeypatch.undo()


# --- profiles ---------------------------------------------------------------


@pytest.fixture
def profiles_dir(tmp_path: Path) -> Path:
    """An empty, writable profiles directory.

    Always prefer this over the repo's real `profiles/`: `YamlProfileRepository()`
    with no argument writes to the checked-in directory.
    """
    directory = tmp_path / "profiles"
    directory.mkdir()
    return directory


@pytest.fixture
def yaml_repo(profiles_dir: Path) -> YamlProfileRepository:
    return YamlProfileRepository(profiles_dir)


@pytest.fixture
def generic_profile_payload() -> dict:
    """The real `generic` profile as stored on disk (read-only use)."""
    return YamlProfileRepository(REAL_PROFILES_DIR).get_profile("generic")


# --- settings ---------------------------------------------------------------


@pytest.fixture
def default_settings() -> Settings:
    return Settings()


@pytest.fixture
def offline_settings() -> Settings:
    """Deterministic settings for pipeline runs: no network sources needed."""
    return Settings.from_dict(
        {
            "profile": "generic",
            "search": {"enabled_sources": [], "max_queries_per_run": 4},
            "selection": {"enabled": True, "top_n": 10, "min_relevance": 30.0},
        }
    )


# --- HTTP -------------------------------------------------------------------


@pytest.fixture
def captured_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record backoff sleeps instead of actually waiting.

    Patches the module-level indirections in `core.util.http`, which is why
    those exist: retry timing is testable without slowing the suite down.
    """
    sleeps: list[float] = []
    monkeypatch.setattr("core.util.http._sleep", sleeps.append)
    monkeypatch.setattr("core.util.http._jitter_random", lambda: 0.0)
    return sleeps


@pytest.fixture
def patched_session(monkeypatch: pytest.MonkeyPatch):
    """Install a scripted session as the shared `core.util.http` session.

    Source adapters call `request_json` without a `session=` argument, so this
    is the seam for adapter-level tests.
    """

    def install(session: object) -> object:
        monkeypatch.setattr("core.util.http._get_session", lambda: session)
        return session

    return install


@pytest.fixture
def errors() -> list[dict]:
    """The shared error sink every source adapter appends to."""
    return []
