from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Settings
from core.repositories.factory import build_profile_repository
from core.repositories.http_profile_repository import HttpProfileRepository
from core.repositories.yaml_profile_repository import YamlProfileRepository


def test_factory_returns_yaml_repository_for_local_mode() -> None:
    settings = Settings.from_dict({"profile_repository": {"mode": "local"}})
    repository = build_profile_repository(settings)
    assert isinstance(repository, YamlProfileRepository)


def test_factory_returns_http_repository_for_remote_mode() -> None:
    settings = Settings.from_dict(
        {
            "profile_repository": {
                "mode": "remote",
                "base_url": "https://example.org",
                "timeout_seconds": 11,
                "max_attempts": 4,
                "backoff_base_seconds": 0.25,
                "backoff_max_seconds": 2.0,
                "headers": {"Authorization": "Bearer token"},
            }
        }
    )
    repository = build_profile_repository(settings)
    assert isinstance(repository, HttpProfileRepository)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All repository factory tests passed.")
