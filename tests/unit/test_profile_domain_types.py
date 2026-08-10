"""Unit tests for the transport-agnostic profile types in
`core.repositories.profile_repository`.
"""

from __future__ import annotations

import pytest

from core.repositories.profile_repository import (
    Bucket,
    DomainProfile,
    ProfileRepository,
    ProfileSummary,
)


def test_from_dict_requires_a_name() -> None:
    with pytest.raises(KeyError):
        DomainProfile.from_dict({"label": "No name"})


def test_from_dict_defaults_the_label_to_the_name() -> None:
    assert DomainProfile.from_dict({"name": "generic"}).label == "generic"


def test_from_dict_coerces_yaml_scalars_to_strings() -> None:
    """YAML parses bare `5` as an int; term lists must stay comparable strings."""
    profile = DomainProfile.from_dict(
        {
            "name": "p",
            "off_topic_terms": [5, True, "text"],
            "term_groups": {"g": [1.5]},
            "concepts": [{"name": "c", "triggers": [7], "terms": [8]}],
        }
    )

    assert profile.off_topic_terms == ["5", "True", "text"]
    assert profile.term_groups["g"] == ["1.5"]
    assert profile.concepts[0].triggers == ["7"]


def test_from_dict_tolerates_null_collections() -> None:
    profile = DomainProfile.from_dict(
        {"name": "p", "query_groups": None, "intents": None, "journal_terms": None}
    )

    assert profile.query_groups == {}
    assert profile.intents == {}
    assert profile.journal_terms == []


def test_term_group_lookup_returns_an_empty_list_for_unknown_groups() -> None:
    profile = DomainProfile.from_dict({"name": "p", "term_groups": {"g": ["a"]}})

    assert profile.term_group("g") == ["a"]
    assert profile.term_group("missing") == []


def test_fallback_bucket_is_the_declared_one_when_present() -> None:
    profile = DomainProfile(
        name="p",
        buckets=[Bucket(id="core", label="Core"), Bucket(id="rest", label="Rest", fallback=True)],
    )

    assert profile.fallback_bucket.id == "rest"


def test_fallback_bucket_is_synthesised_when_a_profile_declares_none() -> None:
    """Ranking always needs somewhere to put an unmatched paper."""
    profile = DomainProfile(name="p", buckets=[Bucket(id="core", label="Core")])

    assert profile.fallback_bucket.id == "all"
    assert profile.fallback_bucket.fallback is True


def test_extraction_fields_carry_the_numeric_requirement() -> None:
    profile = DomainProfile.from_dict(
        {"name": "p", "extraction_fields": [{"name": "Loading", "terms": ["chlorine"], "require_numeric": 1}]}
    )

    assert profile.extraction_fields[0].require_numeric is True


def test_profile_summary_serialises_with_the_api_key_names() -> None:
    summary = ProfileSummary(
        profile_id="generic",
        label="Generic",
        created_at="2026-08-06T00:00:00+00:00",
        updated_at="2026-08-06T00:00:00+00:00",
        is_builtin=True,
    )

    assert summary.to_dict() == {
        "id": "generic",
        "label": "Generic",
        "created_at": "2026-08-06T00:00:00+00:00",
        "updated_at": "2026-08-06T00:00:00+00:00",
        "is_builtin": True,
    }


def test_the_repository_contract_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        ProfileRepository()  # type: ignore[abstract]
