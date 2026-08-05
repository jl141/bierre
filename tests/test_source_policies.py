"""Source dispatch policy tests.

Run with: python tests/test_source_policies.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Settings
from core.pipeline import _plan_search_tasks
from core.sources import SourceDispatchState, policy_for


def _settings(enabled_sources: list[str], *, s2_budget: int = 0, s2_key: str = "") -> Settings:
    return Settings.from_dict(
        {
            "api_keys": {"semantic_scholar": s2_key},
            "search": {
                "enabled_sources": enabled_sources,
                "semantic_scholar_max_queries_without_key": s2_budget,
            },
        }
    )


def test_default_policy_allows_and_is_concurrent() -> None:
    state = SourceDispatchState()
    settings = Settings()
    policy = policy_for("openalex")
    assert policy.allow_dispatch(settings, state)
    assert not policy.force_serial(settings, state)


def test_crossref_and_pubmed_are_forced_serial() -> None:
    settings = _settings(["openalex", "crossref", "pubmed"])
    concurrent, serial, apis = _plan_search_tasks(["q1"], settings)

    assert ("openalex", "q1") in concurrent
    assert ("crossref", "q1") in serial
    assert ("pubmed", "q1") in serial
    assert apis == ["openalex", "crossref", "pubmed"]


def test_semantic_scholar_anon_budget_gates_dispatch() -> None:
    settings = _settings(["semantic_scholar"], s2_budget=1, s2_key="")
    concurrent, serial, apis = _plan_search_tasks(["q1", "q2"], settings)

    assert concurrent == []
    assert serial == [("semantic_scholar", "q1")]
    assert apis == ["semantic_scholar"]


def test_semantic_scholar_with_key_not_gated_or_forced_serial() -> None:
    settings = _settings(["semantic_scholar"], s2_budget=0, s2_key="key")
    concurrent, serial, apis = _plan_search_tasks(["q1", "q2"], settings)

    assert serial == []
    assert concurrent == [("semantic_scholar", "q1"), ("semantic_scholar", "q2")]
    assert apis == ["semantic_scholar"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All source policy tests passed.")
