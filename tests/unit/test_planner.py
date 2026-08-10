"""Unit tests for `core.util.planner` — question -> search queries."""

from __future__ import annotations

from core.repositories.profile_repository import DomainProfile
from core.util.planner import analyze_question, generate_queries
from tests.factories import make_profile


def test_analyze_question_extracts_keywords_without_stopwords() -> None:
    analysis = analyze_question("What is the effect of a coating on adhesion?", make_profile())

    assert "coating" in analysis.keywords
    assert "adhesion" in analysis.keywords
    assert "the" not in analysis.keywords
    assert "of" not in analysis.keywords


def test_analyze_question_detects_scientific_names_but_not_question_words() -> None:
    analysis = analyze_question("Does Escherichia coli survive? What happens with E. coli?", make_profile())

    assert "Escherichia coli" in analysis.scientific_names
    assert "E. coli" in analysis.scientific_names
    assert not any(name.startswith("What ") for name in analysis.scientific_names)


def test_analyze_question_activates_profile_concepts_and_expands_terms() -> None:
    analysis = analyze_question("durable coating for steel", make_profile())

    assert analysis.concepts == ["coating"]
    assert analysis.expanded_terms == ["polyurethane coating", "epoxy coating"]


def test_analyze_question_without_a_trigger_activates_nothing() -> None:
    analysis = analyze_question("unrelated question about turbines", make_profile())

    assert analysis.concepts == []
    assert analysis.expanded_terms == []


def test_generate_queries_always_starts_with_the_raw_question() -> None:
    queries = generate_queries("  durable coating for steel  ", make_profile())

    assert queries[0] == "durable coating for steel"


def test_generate_queries_appends_profile_seed_groups_when_a_concept_is_active() -> None:
    queries = generate_queries("durable coating for steel", make_profile())

    assert "coating durability" in queries
    assert "coating adhesion" in queries


def test_generate_queries_omits_seed_groups_when_no_concept_matches() -> None:
    queries = generate_queries("turbine blade fatigue", make_profile())

    assert "coating durability" not in queries


def test_generate_queries_for_a_bare_profile_is_question_derived_only() -> None:
    queries = generate_queries("graphene supercapacitor electrodes", DomainProfile(name="generic"))

    # Raw question + keyword-derived query only; here both collapse to one entry.
    assert queries == ["graphene supercapacitor electrodes"]


def test_generate_queries_are_unique_and_non_empty() -> None:
    queries = generate_queries("coating coating coating", make_profile())

    assert len(queries) == len(set(q.lower() for q in queries))
    assert all(q.strip() for q in queries)
