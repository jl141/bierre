"""Unit tests for the Semantic Scholar adapter and its dispatch budget."""

from __future__ import annotations

from core.config import Settings
from core.sources import semantic_scholar
from core.sources.policy import SourceDispatchState
from tests.support.http_doubles import FakeResponse, ScriptedSession

ITEM = {
    "title": "Semantic Scholar Paper",
    "authors": [{"name": "Grace Hopper"}, {"name": ""}],
    "year": 2023,
    "venue": "Comp Journal",
    "externalIds": {"DOI": "10.1000/semantic"},
    "abstract": "Paper abstract",
    "url": "https://example.org/semantic",
    "openAccessPdf": {"url": "https://example.org/semantic.pdf"},
    "citationCount": 9,
    "influentialCitationCount": 2,
}


def test_search_maps_an_item_onto_a_paper(ctx, patched_session, errors) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data={"data": [ITEM]})]))

    paper = semantic_scholar.search(ctx, "semantic query")[0]

    assert paper.title == "Semantic Scholar Paper"
    assert paper.authors == "Grace Hopper"  # blank names dropped
    assert paper.doi == "10.1000/semantic"
    assert paper.pdf_url == "https://example.org/semantic.pdf"
    assert paper.oa_status == "open_pdf"
    assert paper.citation_count == 9
    assert paper.influential_citation_count == 2
    assert errors == []


def test_an_api_key_is_sent_as_a_header(make_ctx, patched_session) -> None:
    session = patched_session(ScriptedSession([FakeResponse(json_data={"data": []})]))

    semantic_scholar.search(make_ctx(api_keys={"semantic_scholar": "k1"}), "q")

    assert session.calls[0]["headers"]["X-API-KEY"] == "k1"


def test_the_result_limit_is_capped_at_one_hundred(make_ctx, patched_session) -> None:
    session = patched_session(ScriptedSession([FakeResponse(json_data={"data": []})]))

    semantic_scholar.search(make_ctx(max_results=500), "q")

    assert session.calls[0]["params"]["limit"] == 100


def test_a_non_object_payload_yields_no_papers(ctx, patched_session) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data=["unexpected"])]))

    assert semantic_scholar.search(ctx, "q") == []


def test_a_drifted_payload_shape_is_recorded_not_raised(ctx, patched_session, errors) -> None:
    # `authors` arrives as a scalar instead of a list — iterating it raises.
    patched_session(ScriptedSession([FakeResponse(json_data={"data": [{"authors": 5}]})]))

    assert semantic_scholar.search(ctx, "q") == []
    assert errors[0]["error_type"] == "json_parse_error"


def test_stage_overrides_are_forwarded_and_filtered(make_ctx, monkeypatch) -> None:
    captured: dict = {}

    def fake_request_json(*_args, **kwargs):
        captured.update(kwargs)
        return {"data": []}

    monkeypatch.setattr(semantic_scholar, "request_json", fake_request_json)
    ctx = make_ctx(
        http_overrides={
            "semantic_scholar": {
                "max_attempts": 5,
                "backoff_base_seconds": 0.1,
                "backoff_max_seconds": 1.0,
                "retryable_status_codes": [429, 500, 503],
                "ignored_key": "drop-me",
            }
        }
    )

    semantic_scholar.search(ctx, "q")

    assert captured["max_attempts"] == 5
    assert captured["backoff_base_seconds"] == 0.1
    assert captured["backoff_max_seconds"] == 1.0
    assert captured["retryable_status_codes"] == [429, 500, 503]
    assert "ignored_key" not in captured


# --- dispatch policy ---------------------------------------------------------


def _settings(*, budget: int = 0, key: str = "") -> Settings:
    return Settings.from_dict(
        {
            "api_keys": {"semantic_scholar": key},
            "search": {"semantic_scholar_max_queries_without_key": budget},
        }
    )


def test_anonymous_dispatch_is_capped_by_the_per_run_budget() -> None:
    settings, state = _settings(budget=2), SourceDispatchState()

    assert [semantic_scholar.allow_dispatch(settings, state) for _ in range(3)] == [True, True, False]


def test_a_key_lifts_the_budget_and_allows_concurrency() -> None:
    settings, state = _settings(key="k1"), SourceDispatchState()

    assert semantic_scholar.allow_dispatch(settings, state) is True
    assert semantic_scholar.force_serial(settings, state) is False


def test_anonymous_traffic_is_forced_serial() -> None:
    assert semantic_scholar.force_serial(_settings(), SourceDispatchState()) is True
