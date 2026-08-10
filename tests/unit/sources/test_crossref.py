"""Unit tests for the CrossRef adapter."""

from __future__ import annotations

from core.config import Settings
from core.sources import crossref
from core.sources.policy import SourceDispatchState
from tests.support.http_doubles import FakeResponse, ScriptedSession

ITEM = {
    "title": ["<i>Hydantoin</i> coating &amp; chlorination"],
    "author": [{"given": "Ada", "family": "Lovelace"}, {"family": "Hopper"}],
    "published-print": {"date-parts": [[2024, 3]]},
    "container-title": ["Progress in Coatings"],
    "DOI": "10.1000/CROSSREF",
    "abstract": "<jats:p>An abstract.</jats:p>",
    "URL": "https://doi.org/10.1000/crossref",
}


def test_search_maps_an_item_onto_a_paper(ctx, patched_session, errors) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data={"message": {"items": [ITEM]}})]))

    paper = crossref.search(ctx, "hydantoin coating")[0]

    assert paper.title == "Hydantoin coating & chlorination"  # markup stripped, entities decoded
    assert paper.authors == "Ada Lovelace; Hopper"
    assert paper.year == "2024"
    assert paper.journal == "Progress in Coatings"
    assert paper.doi == "10.1000/crossref"
    assert paper.abstract == "An abstract."
    assert paper.sources == ["CrossRef"]
    assert errors == []


def test_year_falls_through_the_date_field_priority_list(ctx, patched_session) -> None:
    item = {**ITEM}
    del item["published-print"]
    item["created"] = {"date-parts": [[2019, 1, 1]]}
    patched_session(ScriptedSession([FakeResponse(json_data={"message": {"items": [item]}})]))

    assert crossref.search(ctx, "q")[0].year == "2019"


def test_missing_dates_leave_the_year_blank(ctx, patched_session) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data={"message": {"items": [{"title": ["T"]}]}})]))

    assert crossref.search(ctx, "q")[0].year == ""


def test_contact_email_joins_the_polite_pool(make_ctx, patched_session) -> None:
    session = patched_session(ScriptedSession([FakeResponse(json_data={})]))

    crossref.search(make_ctx(email="me@example.org"), "q")

    assert session.calls[0]["params"]["mailto"] == "me@example.org"


def test_an_empty_payload_yields_no_papers(ctx, patched_session, errors) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data={})]))

    assert crossref.search(ctx, "q") == []
    assert errors == []


def test_crossref_is_always_dispatched_serially() -> None:
    assert crossref.force_serial(Settings(), SourceDispatchState()) is True
