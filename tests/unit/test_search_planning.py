"""Unit tests for `core.pipeline._plan_search_tasks` — which (source, query)
pairs run concurrently, which run serially, and which are dropped.
"""

from __future__ import annotations

from core.config import Settings
from core.pipeline import _plan_search_tasks


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


def test_crossref_and_pubmed_are_planned_serially() -> None:
    concurrent, serial, apis = _plan_search_tasks(["q1"], _settings(["openalex", "crossref", "pubmed"]))

    assert concurrent == [("openalex", "q1")]
    assert serial == [("crossref", "q1"), ("pubmed", "q1")]
    assert apis == ["openalex", "crossref", "pubmed"]


def test_the_anonymous_semantic_scholar_budget_drops_extra_queries() -> None:
    concurrent, serial, apis = _plan_search_tasks(["q1", "q2"], _settings(["semantic_scholar"], s2_budget=1))

    assert concurrent == []
    assert serial == [("semantic_scholar", "q1")]
    assert apis == ["semantic_scholar"]


def test_a_semantic_scholar_key_removes_both_the_budget_and_the_serial_rule() -> None:
    concurrent, serial, apis = _plan_search_tasks(["q1", "q2"], _settings(["semantic_scholar"], s2_key="key"))

    assert serial == []
    assert concurrent == [("semantic_scholar", "q1"), ("semantic_scholar", "q2")]
    assert apis == ["semantic_scholar"]


def test_unknown_source_names_in_config_are_ignored() -> None:
    concurrent, serial, apis = _plan_search_tasks(["q1"], _settings(["openalex", "not-a-source"]))

    assert concurrent == [("openalex", "q1")]
    assert serial == []
    assert apis == ["openalex"]


def test_no_queries_means_no_work_and_no_reported_apis() -> None:
    assert _plan_search_tasks([], _settings(["openalex"])) == ([], [], [])


def test_apis_used_lists_each_source_once_across_queries() -> None:
    _concurrent, _serial, apis = _plan_search_tasks(["q1", "q2", "q3"], _settings(["openalex"]))

    assert apis == ["openalex"]
