"""Unit tests for the OpenAlex adapter."""

from __future__ import annotations

from core.sources import openalex
from tests.support.http_doubles import FakeResponse, ScriptedSession

WORK = {
    "title": "Rechargeable coating paper",
    "authorships": [
        {"author": {"display_name": "Ada Lovelace"}},
        {"author": {"display_name": "Grace Hopper"}},
    ],
    "publication_year": 2025,
    "primary_location": {
        "source": {"display_name": "Materials Journal"},
        "landing_page_url": "https://example.org/paper",
        "pdf_url": "https://example.org/paper.pdf",
    },
    "doi": "https://doi.org/10.1000/example",
    "abstract_inverted_index": {"rechargeable": [0], "coating": [1], "study": [2]},
    "open_access": {"is_oa": True, "oa_status": "gold"},
    "cited_by_count": 12,
}


def test_search_maps_a_work_onto_a_paper(ctx, patched_session, errors: list[dict]) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data={"results": [WORK]})]))

    papers = openalex.search(ctx, "rechargeable coating")

    assert len(papers) == 1
    paper = papers[0]
    assert paper.title == "Rechargeable coating paper"
    assert paper.authors == "Ada Lovelace; Grace Hopper"
    assert paper.year == "2025"
    assert paper.journal == "Materials Journal"
    assert paper.doi == "10.1000/example"
    assert paper.abstract == "rechargeable coating study"  # inverted index reassembled in order
    assert paper.pdf_url == "https://example.org/paper.pdf"
    assert paper.oa_status == "gold"
    assert paper.citation_count == 12
    assert paper.sources == ["OpenAlex"]
    assert paper.search_queries == ["rechargeable coating"]
    assert errors == []


def test_search_sends_polite_pool_and_key_parameters(make_ctx, patched_session) -> None:
    session = patched_session(ScriptedSession([FakeResponse(json_data={"results": []})]))
    ctx = make_ctx(email="me@example.org", api_keys={"openalex": " k1 "}, max_results=7)

    openalex.search(ctx, "q")

    params = session.calls[0]["params"]
    assert params["search"] == "q"
    assert params["per-page"] == 7
    assert params["mailto"] == "me@example.org"
    assert params["api_key"] == "k1"


def test_a_failed_request_yields_no_papers_and_one_recorded_error(ctx, patched_session, errors) -> None:
    patched_session(ScriptedSession([FakeResponse(status_code=404, reason="Not Found")]))

    assert openalex.search(ctx, "q") == []
    assert len(errors) == 1
    assert errors[0]["stage"] == "openalex"


def test_missing_optional_fields_degrade_to_empty_strings(ctx, patched_session) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data={"results": [{"display_name": "Fallback title"}]})]))

    paper = openalex.search(ctx, "q")[0]

    assert paper.title == "Fallback title"
    assert (paper.authors, paper.year, paper.journal, paper.doi, paper.abstract) == ("", "", "", "", "")


def test_per_stage_http_overrides_reach_the_helper(make_ctx, monkeypatch) -> None:
    captured: dict = {}

    def fake_request_json(*_args, **kwargs):
        captured.update(kwargs)
        return {"results": []}

    monkeypatch.setattr(openalex, "request_json", fake_request_json)
    ctx = make_ctx(http_overrides={"openalex": {"max_attempts": 5, "ignored_key": "drop-me"}})

    openalex.search(ctx, "q")

    assert captured["max_attempts"] == 5
    assert "ignored_key" not in captured
