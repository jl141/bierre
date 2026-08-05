"""Integration test: settings YAML -> pipeline context -> stage HTTP options."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Settings
from core.pipeline import _search


def test_yaml_overrides_flow_into_stage_http_options() -> None:
    config_obj = {
        "profile": "generic",
        "search": {
            "enabled_sources": ["semantic_scholar"],
            "timeout_seconds": 11,
            "semantic_scholar_max_queries_without_key": 1,
            "source_http_overrides": {
                "semantic_scholar": {
                    "max_attempts": 5,
                    "backoff_base_seconds": 0.15,
                    "backoff_max_seconds": 0.9,
                    "retryable_status_codes": [429, 500, 503],
                }
            },
        },
    }

    with TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_path.write_text(json.dumps(config_obj), encoding="utf-8")
        settings = Settings.load(config_path)

    seen: dict[str, object] = {}

    def fake_source(ctx, query):
        seen["query"] = query
        seen["timeout"] = ctx.timeout
        seen["options"] = ctx.http_options("semantic_scholar")
        return []

    errors: list[dict] = []
    with patch.dict("core.pipeline.REGISTRY", {"semantic_scholar": fake_source}, clear=False):
        papers, apis = _search(["test query"], settings, errors, None)

    assert papers == []
    assert apis == ["semantic_scholar"]
    assert errors == []
    assert seen["query"] == "test query"
    assert seen["timeout"] == 11
    assert seen["options"] == {
        "max_attempts": 5,
        "backoff_base_seconds": 0.15,
        "backoff_max_seconds": 0.9,
        "retryable_status_codes": [429, 500, 503],
    }


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All HTTP override integration tests passed.")
