"""Unit tests for `core.utils.extraction` — rule-based evidence rows."""

from __future__ import annotations

from core.repositories.profile_repository import DomainProfile, ExtractionField
from core.utils.extraction import extract
from tests.factories import make_paper, make_profile, make_ranked_paper


def _row_for(abstract: str, profile: DomainProfile | None = None):
    ranked = make_ranked_paper(make_paper(abstract=abstract, paper_id="P0007", doi="10.1/x"))
    return extract([ranked], profile or make_profile())[0]


def test_extract_reports_matched_terms_and_supporting_sentences() -> None:
    row = _row_for("The coating carries N-halamine groups. Active chlorine reached 0.42 wt%.")

    assert row.paper_id == "P0007"
    assert row.fields["Chemistry"].startswith("Detected: n-halamine, active chlorine.")
    assert "Active chlorine reached 0.42 wt%." in row.fields["Chemistry"]


def test_require_numeric_skips_sentences_without_a_number() -> None:
    with_number = _row_for("Active chlorine reached 0.42 wt%.")
    without_number = _row_for("Active chlorine was present in the coating.")

    assert with_number.fields["Loading"].startswith("Detected:")
    assert without_number.fields["Loading"] == "Not reported"


def test_missing_evidence_is_reported_not_omitted() -> None:
    row = _row_for("A study of turbine blades.")

    assert row.fields == {"Chemistry": "Not reported", "Loading": "Not reported"}


def test_negated_mentions_do_not_count_as_evidence() -> None:
    row = _row_for("The study did not report active chlorine.")

    assert row.fields["Chemistry"] == "Not reported"


def test_at_most_two_supporting_sentences_are_kept() -> None:
    body = " ".join(f"Active chlorine result number {i}." for i in range(5))

    row = _row_for(body)

    assert row.fields["Chemistry"].count("Active chlorine result number") == 2


def test_extract_falls_back_to_the_title_when_there_is_no_abstract() -> None:
    ranked = make_ranked_paper(make_paper(title="Active chlorine coating.", abstract="", paper_id="P1"))

    row = extract([ranked], make_profile())[0]

    assert row.fields["Chemistry"].startswith("Detected: active chlorine")


def test_a_profile_without_extraction_fields_yields_empty_rows() -> None:
    ranked = make_ranked_paper()

    rows = extract([ranked], DomainProfile(name="bare"))

    assert rows[0].fields == {}
    assert rows[0].to_dict() == {"paper_id": "P0001", "title": "Sample paper", "doi": "10.1000/test"}


def test_extract_returns_one_row_per_selected_paper() -> None:
    profile = DomainProfile(name="p", extraction_fields=[ExtractionField(name="Any", terms=["coating"])])
    ranked = [
        make_ranked_paper(make_paper(paper_id="P0001", abstract="A coating.")),
        make_ranked_paper(make_paper(paper_id="P0002", abstract="No match here.")),
    ]

    rows = extract(ranked, profile)

    assert [row.paper_id for row in rows] == ["P0001", "P0002"]
