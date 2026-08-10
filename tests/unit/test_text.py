"""Unit tests for `core.util.text` — the pure helpers everything else leans on."""

from __future__ import annotations

import pytest

from core.util import text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  a   b\n\tc ", "a b c"),
        ("a\x00b", "a b"),
        (None, ""),
        (42, "42"),
    ],
)
def test_compact_whitespace_collapses_runs_and_control_chars(value, expected) -> None:
    assert text.compact_whitespace(value) == expected


def test_strip_markup_unescapes_entities_and_drops_tags() -> None:
    assert text.strip_markup("<p>Ca&amp;Mg <b>coating</b></p>") == "Ca&Mg coating"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://doi.org/10.1000/ABC.123", "10.1000/abc.123"),
        ("doi:10.1000/abc", "10.1000/abc"),
        ("10.1000/abc.", "10.1000/abc"),
        ("not a doi", "not a doi"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_doi(raw, expected) -> None:
    assert text.normalize_doi(raw) == expected


def test_normalize_title_is_a_punctuation_free_dedup_key() -> None:
    assert text.normalize_title("N-Halamine: A Review!") == "n halamine a review"
    assert text.normalize_title("<i>N-Halamine</i>—A Review") == text.normalize_title("N-halamine, a review")


def test_tokenize_keeps_chemical_style_identifiers() -> None:
    # Hyphens, dots and slashes stay inside a token; single characters are dropped.
    assert text.tokenize("N-halamine PU-coating 5,5-dimethylhydantoin a") == [
        "n-halamine",
        "pu-coating",
        "5-dimethylhydantoin",
    ]


def test_split_sentences_handles_empty_and_multi_sentence_text() -> None:
    assert text.split_sentences("   ") == []
    assert text.split_sentences("First one. Second one! Third?") == ["First one.", "Second one!", "Third?"]


@pytest.mark.parametrize(
    ("body", "term", "expected"),
    [
        ("A pump was used", "pu", False),  # word boundary: 'pu' is not inside 'pump'
        ("A PU coating", "pu", True),
        ("active   chlorine content", "active chlorine", True),  # spaces match any whitespace run
        ("anything", "", False),
    ],
)
def test_contains_is_whole_token_and_case_insensitive(body, term, expected) -> None:
    assert text.contains(body, term) is expected


def test_has_unnegated_rejects_terms_behind_a_negation_cue() -> None:
    negated = "It did not report N-halamine chemistry."
    assert text.contains(negated, "n-halamine") is True
    assert text.has_unnegated(negated, "n-halamine") is False


def test_has_unnegated_accepts_a_positive_mention_elsewhere() -> None:
    body = "It did not report silver. The coating shows N-halamine activity."
    assert text.has_unnegated(body, "n-halamine") is True


def test_matched_terms_preserves_order_and_deduplicates() -> None:
    body = "Chlorine and hydantoin and chlorine again."
    assert text.matched_terms(body, ["hydantoin", "chlorine", "hydantoin"]) == ["hydantoin", "chlorine"]


def test_matched_terms_can_require_unnegated_hits() -> None:
    body = "No hydantoin was used. Chlorine was measured."
    assert text.matched_terms(body, ["hydantoin", "chlorine"], unnegated=True) == ["chlorine"]


def test_best_snippet_picks_the_densest_sentence_and_truncates() -> None:
    body = "Intro sentence. Hydantoin and chlorine were both measured. Outro."
    assert text.best_snippet(body, ["hydantoin", "chlorine"]) == "Hydantoin and chlorine were both measured."

    long_sentence = " ".join(["word"] * 100) + "."
    snippet = text.best_snippet(long_sentence, ["word"], max_words=5)
    assert snippet == "word word word word word..."


def test_best_snippet_of_empty_text_is_empty() -> None:
    assert text.best_snippet("", ["anything"]) == ""
