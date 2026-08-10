"""Unit tests for the Unpaywall open-access enrichment step."""

from __future__ import annotations

from core.sources import unpaywall
from tests.factories import make_paper
from tests.support.http_doubles import FakeResponse, ScriptedSession


def test_enrichment_is_skipped_without_a_contact_email(ctx, errors) -> None:
    paper = make_paper(pdf_url="")

    unpaywall.enrich([paper], ctx)

    assert paper.pdf_url == ""
    assert errors[0]["error_type"] == "configuration_error"
    assert "contact_email" in errors[0]["message"]


def test_enrichment_fills_the_open_access_pdf(make_ctx, patched_session) -> None:
    patched_session(
        ScriptedSession(
            [
                FakeResponse(
                    json_data={
                        "oa_status": "gold",
                        "best_oa_location": {"url_for_pdf": "https://example.org/best.pdf"},
                    }
                )
            ]
        )
    )
    paper = make_paper(doi="10.1000/test", pdf_url="")

    unpaywall.enrich([paper], make_ctx(email="me@example.org"))

    assert paper.pdf_url == "https://example.org/best.pdf"
    assert paper.oa_status == "gold"


def test_any_oa_location_is_used_when_the_best_one_has_no_pdf(make_ctx, patched_session) -> None:
    patched_session(
        ScriptedSession(
            [
                FakeResponse(
                    json_data={
                        "is_oa": True,
                        "best_oa_location": {},
                        "oa_locations": [{}, {"url_for_pdf": "https://example.org/other.pdf"}],
                    }
                )
            ]
        )
    )
    paper = make_paper(doi="10.1000/test", pdf_url="")

    unpaywall.enrich([paper], make_ctx(email="me@example.org"))

    assert paper.pdf_url == "https://example.org/other.pdf"
    assert paper.oa_status == "oa"


def test_a_closed_paper_keeps_its_existing_pdf_link(make_ctx, patched_session) -> None:
    patched_session(ScriptedSession([FakeResponse(json_data={"is_oa": False})]))
    paper = make_paper(doi="10.1000/test", pdf_url="https://example.org/original.pdf")

    unpaywall.enrich([paper], make_ctx(email="me@example.org"))

    assert paper.oa_status == "closed"
    assert paper.pdf_url == "https://example.org/original.pdf"


def test_supporting_information_suffixes_are_stripped_from_the_doi(make_ctx, patched_session) -> None:
    session = patched_session(ScriptedSession([FakeResponse(json_data={})]))

    unpaywall.enrich([make_paper(doi="10.1000/test.s001")], make_ctx(email="me@example.org"))

    assert session.calls[0]["url"].endswith("/10.1000/test")


def test_papers_without_a_doi_are_skipped(make_ctx, patched_session) -> None:
    session = patched_session(ScriptedSession([]))

    unpaywall.enrich([make_paper(doi="")], make_ctx(email="me@example.org"))

    assert session.calls == []
