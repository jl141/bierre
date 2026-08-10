"""Unit tests for `core.util.dedup`."""

from __future__ import annotations

from core.util.dedup import deduplicate
from tests.factories import make_paper


def test_dedup_merges_by_doi_and_keeps_the_richer_record() -> None:
    merged = deduplicate(
        [
            make_paper(doi="10.1/x", abstract="short", sources=["OpenAlex"], search_queries=["q1"], paper_id=""),
            make_paper(
                doi="https://doi.org/10.1/X",
                abstract="a much longer abstract",
                sources=["CrossRef"],
                search_queries=["q2"],
                journal="",
                paper_id="",
            ),
        ]
    )

    assert len(merged) == 1
    assert merged[0].abstract == "a much longer abstract"
    assert set(merged[0].sources) == {"OpenAlex", "CrossRef"}
    assert merged[0].search_queries == ["q1", "q2"]
    assert merged[0].paper_id == "P0001"


def test_dedup_falls_back_to_the_normalised_title_when_no_doi() -> None:
    merged = deduplicate(
        [
            make_paper(title="A Study!", doi="", pdf_url="", paper_id=""),
            make_paper(title="a study", doi="", pdf_url="https://example.org/a.pdf", paper_id=""),
        ]
    )

    assert len(merged) == 1
    # Blank scalar fields are filled from the duplicate; non-blank ones are kept.
    assert merged[0].pdf_url == "https://example.org/a.pdf"


def test_dedup_keeps_untitled_doi_less_records_apart() -> None:
    merged = deduplicate([make_paper(title="", doi="", paper_id=""), make_paper(title="", doi="", paper_id="")])

    assert [p.paper_id for p in merged] == ["P0001", "P0002"]


def test_dedup_prefers_the_first_non_null_metric() -> None:
    merged = deduplicate(
        [
            make_paper(doi="10.1/x", citation_count=None, impact_factor=None, paper_id=""),
            make_paper(doi="10.1/x", citation_count=12, impact_factor=3.4, paper_id=""),
        ]
    )

    assert merged[0].citation_count == 12
    assert merged[0].impact_factor == 3.4


def test_dedup_renumbers_paper_ids_in_first_seen_order() -> None:
    merged = deduplicate(
        [
            make_paper(title="B", doi="10.1/b", paper_id="P9999"),
            make_paper(title="A", doi="10.1/a", paper_id="P0001"),
        ]
    )

    assert [(p.title, p.paper_id) for p in merged] == [("B", "P0001"), ("A", "P0002")]
