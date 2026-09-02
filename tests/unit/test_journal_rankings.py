"""Unit tests for `core.utils.journal_rankings`."""

from __future__ import annotations

import pytest

from core.utils import journal_rankings
from core.utils.journal_rankings import impact_factor_for_journal


@pytest.fixture(autouse=True)
def _clear_ranking_cache():
    """The TSV is memoised with `lru_cache`; drop it around cache-sensitive tests."""
    journal_rankings._rankings.cache_clear()
    yield
    journal_rankings._rankings.cache_clear()


def test_lookup_is_case_and_punctuation_insensitive() -> None:
    assert impact_factor_for_journal("nature") == 56.1
    assert impact_factor_for_journal("Nature") == 56.1
    assert impact_factor_for_journal("  NATURE  ") == 56.1


def test_unknown_or_blank_journal_returns_none() -> None:
    assert impact_factor_for_journal("") is None
    assert impact_factor_for_journal("Journal Of Nothing At All") is None


def test_missing_rankings_file_degrades_to_no_data(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(journal_rankings, "_RANKINGS_FILE", tmp_path / "absent.tsv")
    journal_rankings._rankings.cache_clear()

    assert impact_factor_for_journal("nature") is None


def test_malformed_rows_are_skipped(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    tsv = tmp_path / "rankings.tsv"
    tsv.write_text("Good Journal\t9.5\nBad Journal\tnot-a-number\n\nNo Tab Here\n", encoding="utf-8")
    monkeypatch.setattr(journal_rankings, "_RANKINGS_FILE", tsv)
    journal_rankings._rankings.cache_clear()

    assert impact_factor_for_journal("Good Journal") == 9.5
    assert impact_factor_for_journal("Bad Journal") is None
    assert impact_factor_for_journal("No Tab Here") is None
