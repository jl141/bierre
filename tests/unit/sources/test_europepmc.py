"""Unit tests for the Europe PMC adapter."""

from __future__ import annotations

from core.sources import europepmc
from tests.support.http_doubles import FakeResponse, ScriptedSession

RESULT = {
    "title": "Antimicrobial dressing study",
    "authorString": "Lovelace A, Hopper G.",
    "pubYear": "2022",
    "journalTitle": "Journal of Wound Care",
    "doi": "10.1000/EPMC",
    "abstractText": "<p>Abstract body.</p>",
    "source": "MED",
    "id": "12345",
    "isOpenAccess": "Y",
    "fullTextUrlList": {
        "fullTextUrl": [
            {"documentStyle": "html", "availability": "Open access", "url": "https://example.org/html"},
            {"documentStyle": "pdf", "availability": "Open access", "url": "https://example.org/paper.pdf"},
        ]
    },
}


def _payload(result: dict) -> dict:
    return {"resultList": {"result": [result]}}


def test_search_maps_a_result_onto_a_paper(ctx, patched_session, errors) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data=_payload(RESULT))]))

    paper = europepmc.search(ctx, "wound dressing")[0]

    assert paper.title == "Antimicrobial dressing study"
    assert paper.journal == "Journal of Wound Care"
    assert paper.doi == "10.1000/epmc"
    assert paper.abstract == "Abstract body."
    assert paper.url == "https://europepmc.org/article/MED/12345"
    assert paper.pdf_url == "https://example.org/paper.pdf"  # only the open PDF entry
    assert paper.oa_status == "Y"
    assert paper.sources == ["EuropePMC"]
    assert errors == []


def test_article_url_falls_back_to_the_doi(ctx, patched_session) -> None:
    result = {k: v for k, v in RESULT.items() if k not in {"source", "id"}}
    patched_session(ScriptedSession([FakeResponse(json_data=_payload(result))]))

    assert europepmc.search(ctx, "q")[0].url == "https://doi.org/10.1000/epmc"


def test_a_paywalled_pdf_entry_is_ignored(ctx, patched_session) -> None:
    result = {
        **RESULT,
        "fullTextUrlList": {
            "fullTextUrl": [
                {"documentStyle": "pdf", "availability": "Subscription required", "url": "https://paywall"}
            ]
        },
    }
    patched_session(ScriptedSession([FakeResponse(json_data=_payload(result))]))

    assert europepmc.search(ctx, "q")[0].pdf_url == ""


def test_page_size_follows_max_results(make_ctx, patched_session) -> None:
    session = patched_session(ScriptedSession([FakeResponse(json_data={})]))

    europepmc.search(make_ctx(max_results=25), "q")

    assert session.calls[0]["params"]["pageSize"] == 25
    assert session.calls[0]["params"]["format"] == "json"


def test_an_empty_result_list_yields_no_papers(ctx, patched_session) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data={"resultList": {"result": []}})]))

    assert europepmc.search(ctx, "q") == []
