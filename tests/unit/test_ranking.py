"""Unit tests for `core.utils.ranking`.

Absolute relevance numbers depend on which optional libraries are installed
(rank-bm25 / scikit-learn / rapidfuzz), so these tests assert *ordering,
classification and selection* — the parts that must hold either way.
"""

from __future__ import annotations

import sys

import pytest

from core.config import Settings
from core.repositories.profile_repository import Bucket, DomainProfile
from core.utils.ranking import rank_and_select
from tests.factories import make_paper, make_profile

QUESTION = "rechargeable N-halamine polyurethane coating"


def _core_paper() -> object:
    return make_paper(
        title="Rechargeable N-halamine polyurethane coating",
        abstract="A polyurethane coating with N-halamine active chlorine, recharged over 10 cycles.",
        journal="Progress in Organic Coatings",
        doi="10.1/core",
        paper_id="",
    )


def _adjacent_paper() -> object:
    return make_paper(
        title="N-halamine cotton textile",
        abstract="Cotton textile grafted with hydantoin showing active chlorine.",
        journal="Textile Research",
        doi="10.1/adjacent",
        paper_id="",
    )


def _offtopic_paper() -> object:
    return make_paper(
        title="Silver nanoparticle hydrogel dressing",
        abstract="A silver nanoparticle hydrogel dressing. It did not report active chlorine.",
        journal="Nanomedicine",
        doi="10.1/offtopic",
        paper_id="",
    )


def _rank(papers, profile=None, settings=None):
    return rank_and_select(list(papers), QUESTION, profile or make_profile(), settings or Settings())


def test_papers_are_classified_into_the_first_matching_bucket() -> None:
    ranked = _rank([_core_paper(), _adjacent_paper(), _offtopic_paper()])
    buckets = {item.paper.doi: item.bucket for item in ranked}

    assert buckets["10.1/core"] == "core"
    assert buckets["10.1/adjacent"] == "adjacent"
    assert buckets["10.1/offtopic"] == "other"


def test_bucket_order_dominates_the_final_ordering() -> None:
    ranked = _rank([_offtopic_paper(), _adjacent_paper(), _core_paper()])

    assert [item.bucket for item in ranked] == ["core", "adjacent", "other"]
    assert [item.rank for item in ranked] == [1, 2, 3]


def test_off_topic_terms_penalise_a_fallback_bucket_paper() -> None:
    ranked = _rank([_offtopic_paper()])

    assert ranked[0].bucket == "other"
    assert ranked[0].off_topic_penalty >= 15.0
    assert any("off-topic penalty" in reason for reason in ranked[0].reasons)


def test_exclude_off_topic_bucket_rejects_a_paper_carrying_an_off_topic_term() -> None:
    paper = make_paper(
        title="N-halamine polyurethane coating with silver nanoparticle filler",
        abstract="Polyurethane coating with N-halamine active chlorine and silver nanoparticle additives.",
        doi="10.1/mixed",
        paper_id="",
    )

    ranked = _rank([paper])

    # `core` requires both term groups but excludes off-topic papers, so the
    # paper falls through to the next bucket that still matches.
    assert ranked[0].bucket == "adjacent"


def test_matched_terms_are_reported_per_group() -> None:
    ranked = _rank([_core_paper()])

    assert ranked[0].matched["chemistry"] == ["n-halamine", "active chlorine"]
    assert ranked[0].matched["substrate"] == ["polyurethane"]


def test_negated_terms_do_not_count_as_matches() -> None:
    paper = make_paper(
        title="Coating study",
        abstract="The coating did not report active chlorine.",
        doi="10.1/negated",
        paper_id="",
    )

    ranked = _rank([paper])

    assert ranked[0].matched["chemistry"] == []
    assert ranked[0].bucket == "other"


def test_selection_disabled_selects_everything() -> None:
    settings = Settings.from_dict({"selection": {"enabled": False}})

    ranked = _rank([_core_paper(), _offtopic_paper()], settings=settings)

    assert all(item.selected for item in ranked)


def test_selection_top_n_caps_the_selected_set() -> None:
    settings = Settings.from_dict({"selection": {"enabled": True, "top_n": 1, "min_relevance": 0.0}})

    ranked = _rank([_core_paper(), _adjacent_paper(), _offtopic_paper()], settings=settings)

    assert sum(1 for item in ranked if item.selected) == 1
    assert ranked[0].selected is True


def test_fallback_papers_must_clear_the_relevance_floor() -> None:
    settings = Settings.from_dict({"selection": {"enabled": True, "top_n": 25, "min_relevance": 99.9}})

    ranked = _rank([_core_paper(), _offtopic_paper()], settings=settings)
    selected = {item.paper.doi for item in ranked if item.selected}

    # The on-topic paper is a candidate regardless of score; the fallback one is not.
    assert "10.1/core" in selected
    assert "10.1/offtopic" not in selected


def test_when_no_candidate_clears_the_floor_everything_stays_eligible() -> None:
    """A profile with only a fallback bucket must not return an empty selection."""
    profile = DomainProfile(name="generic", buckets=[Bucket(id="all", label="Relevant", fallback=True)])
    settings = Settings.from_dict({"selection": {"enabled": True, "top_n": 2, "min_relevance": 99.9}})

    ranked = rank_and_select([_core_paper(), _offtopic_paper()], QUESTION, profile, settings)

    assert sum(1 for item in ranked if item.selected) == 2


def test_every_ranked_paper_gets_a_human_readable_explanation() -> None:
    ranked = _rank([_core_paper()])
    item = ranked[0]

    assert item.level in {"High", "Medium", "Low-Medium", "Low"}
    assert item.question_relevance.startswith(item.level)
    assert f"{item.relevance:.0f}%" in item.question_relevance
    assert item.snippet


def test_relevance_and_priority_stay_inside_zero_to_one_hundred() -> None:
    ranked = _rank([_core_paper(), _adjacent_paper(), _offtopic_paper()])

    for item in ranked:
        assert 0.0 <= item.relevance <= 100.0
        assert 0.0 <= item.final_priority <= 100.0


def test_ranking_an_empty_list_returns_an_empty_list() -> None:
    assert _rank([]) == []


@pytest.fixture
def without_optional_ranking_libraries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a bare install: `import x` raises when `sys.modules[x] is None`."""
    for name in (
        "rank_bm25",
        "sklearn",
        "sklearn.feature_extraction",
        "sklearn.feature_extraction.text",
        "sklearn.metrics",
        "sklearn.metrics.pairwise",
        "rapidfuzz",
    ):
        monkeypatch.setitem(sys.modules, name, None)


def test_ranking_still_works_without_the_optional_libraries(without_optional_ranking_libraries) -> None:
    """README promise: missing rank-bm25/scikit-learn/rapidfuzz degrades, never crashes."""
    ranked = _rank([_core_paper(), _offtopic_paper()])

    assert [item.bucket for item in ranked] == ["core", "other"]
    assert ranked[0].relevance > 0.0  # token-overlap fallback still scores
    assert all(0.0 <= item.final_priority <= 100.0 for item in ranked)


def test_metadata_quality_lifts_a_richer_record(without_optional_ranking_libraries) -> None:
    """With the lexical libraries gone, the quality signal is observable on its own."""
    bare = make_paper(title="Coating study", abstract="", doi="", journal="", year="", paper_id="")
    rich = make_paper(
        title="Coating study",
        abstract="A coating study.",
        doi="10.1/rich",
        pdf_url="https://example.org/a.pdf",
        journal="Progress in Organic Coatings",
        year="2025",
        citation_count=80,
        sources=["OpenAlex", "CrossRef"],
        paper_id="",
    )

    ranked = {item.paper.doi: item for item in _rank([bare, rich])}

    assert ranked["10.1/rich"].relevance > ranked[""].relevance
