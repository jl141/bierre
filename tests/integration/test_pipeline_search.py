"""Online-mode search orchestration with the source registry stubbed out.

Covers the path a YAML config takes into a source call — settings file ->
`SearchContext` -> per-stage HTTP options — plus fan-out and error isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from core.config import Settings
from core.models import Paper
from core.pipeline import _search, run_pipeline
from core.sources.base import SearchContext


def test_yaml_overrides_reach_the_stage_http_options(tmp_path: Path) -> None:
    config = {
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
    config_path = tmp_path / "config.yaml"
    config_path.write_text(json.dumps(config), encoding="utf-8")  # JSON is valid YAML
    settings = Settings.load(config_path)

    seen: dict[str, object] = {}

    def fake_source(ctx: SearchContext, query: str) -> list[Paper]:
        seen.update(query=query, timeout=ctx.timeout, options=ctx.http_options("semantic_scholar"))
        return []

    errors: list[dict] = []
    with patch.dict("core.pipeline.REGISTRY", {"semantic_scholar": fake_source}, clear=False):
        papers, apis = _search(["test query"], settings, errors, None)

    assert (papers, apis, errors) == ([], ["semantic_scholar"], [])
    assert seen["query"] == "test query"
    assert seen["timeout"] == 11
    assert seen["options"] == {
        "max_attempts": 5,
        "backoff_base_seconds": 0.15,
        "backoff_max_seconds": 0.9,
        "retryable_status_codes": [429, 500, 503],
    }


def test_concurrent_and_serial_sources_both_contribute_results() -> None:
    settings = Settings.from_dict({"search": {"enabled_sources": ["openalex", "crossref"]}})

    def source(name: str):
        def search(_ctx, query):
            return [Paper(title=f"{name}:{query}", sources=[name])]

        return search

    errors: list[dict] = []
    with patch.dict(
        "core.pipeline.REGISTRY",
        {"openalex": source("openalex"), "crossref": source("crossref")},
        clear=False,
    ):
        papers, apis = _search(["q1"], settings, errors, None)

    assert sorted(p.title for p in papers) == ["crossref:q1", "openalex:q1"]
    assert apis == ["openalex", "crossref"]
    assert errors == []


def test_one_failing_source_never_aborts_the_run() -> None:
    settings = Settings.from_dict({"search": {"enabled_sources": ["openalex", "crossref"]}})

    def boom(_ctx, _query):
        raise RuntimeError("source exploded")

    def ok(_ctx, query):
        return [Paper(title="survivor", sources=["crossref"])]

    errors: list[dict] = []
    with patch.dict("core.pipeline.REGISTRY", {"openalex": boom, "crossref": ok}, clear=False):
        papers, _apis = _search(["q1"], settings, errors, None)

    assert [p.title for p in papers] == ["survivor"]
    assert errors[0] == {"stage": "openalex", "error_type": "workflow_error", "message": "source exploded"}


def test_progress_is_reported_once_per_dispatched_task() -> None:
    settings = Settings.from_dict({"search": {"enabled_sources": ["openalex", "crossref"]}})
    steps: list[tuple[int, int, str]] = []

    with patch.dict(
        "core.pipeline.REGISTRY",
        {"openalex": lambda _c, _q: [], "crossref": lambda _c, _q: []},
        clear=False,
    ):
        _search(["q1"], settings, [], lambda *args: steps.append(args))

    assert len(steps) == 2
    assert [step for step, _t, _l in steps] == [1, 2]


def test_an_online_run_enriches_papers_with_journal_impact_factors() -> None:
    settings = Settings.from_dict({"profile": "generic", "search": {"enabled_sources": ["openalex"]}})

    def source(_ctx, query):
        return [Paper(title="Paper", journal="Nature", doi="10.1/x", abstract="Body", sources=["OpenAlex"])]

    with patch.dict("core.pipeline.REGISTRY", {"openalex": source}, clear=False):
        result = run_pipeline("question about papers", settings)

    assert result.mode == "online"
    assert result.ranked[0].paper.impact_factor == 56.1


def test_unpaywall_enrichment_fills_pdf_links_for_selected_papers(patched_session) -> None:
    from tests.support.http_doubles import FakeResponse, ScriptedSession

    settings = Settings.from_dict(
        {
            "profile": "generic",
            "use_unpaywall": True,
            "contact_email": "me@example.org",
            "search": {"enabled_sources": ["openalex"]},
        }
    )
    patched_session(
        ScriptedSession(
            [
                FakeResponse(
                    json_data={"oa_status": "green", "best_oa_location": {"url_for_pdf": "https://x/a.pdf"}}
                )
            ]
        )
    )

    def source(_ctx, _query):
        return [Paper(title="Paper", doi="10.1/x", abstract="Body", sources=["OpenAlex"])]

    with patch.dict("core.pipeline.REGISTRY", {"openalex": source}, clear=False):
        result = run_pipeline("question about papers", settings)

    assert "unpaywall" in result.apis_used
    assert result.ranked[0].paper.pdf_url == "https://x/a.pdf"
    assert result.ranked[0].paper.oa_status == "green"


def test_unpaywall_enrichment_requires_a_contact_email() -> None:
    settings = Settings.from_dict(
        {"profile": "generic", "use_unpaywall": True, "search": {"enabled_sources": ["openalex"]}}
    )

    def source(_ctx, _query):
        return [Paper(title="Paper", doi="10.1/x", abstract="Body", sources=["OpenAlex"])]

    with patch.dict("core.pipeline.REGISTRY", {"openalex": source}, clear=False):
        result = run_pipeline("question about papers", settings)

    assert "unpaywall" not in result.apis_used
    assert result.errors[0]["error_type"] == "configuration_error"
