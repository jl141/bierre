"""Unit tests for `core.models` — the serialisation surface adapters depend on."""

from __future__ import annotations

from tests.factories import make_evidence_row, make_paper, make_ranked_paper, make_run_result


def test_document_text_weights_the_title_three_times() -> None:
    paper = make_paper(title="Coating", abstract="Body text")

    assert paper.document_text() == "Coating Coating Coating Body text"


def test_classification_text_includes_journal_and_queries() -> None:
    paper = make_paper(
        title="T", abstract="A", journal="Coatings Journal", search_queries=["q1", "q2"]
    )

    assert paper.classification_text() == "T A Coatings Journal q1 q2"


def test_evidence_text_prefers_the_abstract_and_falls_back_to_the_title() -> None:
    assert make_paper(title="T", abstract="A").evidence_text() == "A"
    assert make_paper(title="T", abstract="").evidence_text() == "T"


def test_ranked_paper_status_tracks_selection() -> None:
    assert make_ranked_paper(selected=True).status == "Selected"
    assert make_ranked_paper(selected=False).status == "Not selected"


def test_ranked_paper_to_dict_rounds_scores_and_caps_reasons() -> None:
    item = make_ranked_paper(relevance=88.26, final_priority=90.44, reasons=[f"r{i}" for i in range(8)])

    payload = item.to_dict()

    assert payload["relevance_percent"] == 88.3
    assert payload["final_priority"] == 90.4
    assert payload["reason"] == "r0; r1; r2; r3; r4"  # first five only


def test_ranked_paper_to_dict_prefers_the_bucket_label() -> None:
    assert make_ranked_paper(bucket="core", bucket_label="Core").to_dict()["bucket"] == "Core"
    assert make_ranked_paper(bucket="core", bucket_label="").to_dict()["bucket"] == "core"


def test_evidence_row_flattens_custom_fields_into_the_payload() -> None:
    row = make_evidence_row(fields={"Methods": "Detected: x"})

    assert row.to_dict() == {
        "paper_id": "P0001",
        "title": "Sample paper",
        "doi": "10.1000/test",
        "Methods": "Detected: x",
    }


def test_run_result_selected_and_counts_agree() -> None:
    result = make_run_result(
        ranked=[make_ranked_paper(selected=True), make_ranked_paper(selected=False)]
    )

    assert len(result.selected) == 1
    assert result.to_dict()["counts"] == {"found": 2, "selected": 1}


def test_run_result_to_dict_has_the_documented_top_level_keys() -> None:
    payload = make_run_result().to_dict()

    assert set(payload) == {
        "run_id",
        "timestamp",
        "mode",
        "profile",
        "question",
        "queries",
        "apis_used",
        "counts",
        "papers",
        "evidence",
        "errors",
    }
