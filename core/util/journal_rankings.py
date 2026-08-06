"""Journal impact-factor lookup backed by the bundled OOIR rankings TSV."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from . import text

_RANKINGS_FILE = Path(__file__).resolve().with_name("ooir-journal-rankings-2025.tsv")


@lru_cache(maxsize=1)
def _rankings() -> dict[str, float]:
    rankings: dict[str, float] = {}
    if not _RANKINGS_FILE.exists():
        return rankings
    with open(_RANKINGS_FILE, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            journal, _, factor = line.partition("\t")
            if not journal or not factor:
                continue
            try:
                rankings[text.normalize_title(journal)] = float(factor)
            except ValueError:
                continue
    return rankings


def impact_factor_for_journal(journal: str) -> float | None:
    """Return the OOIR impact factor for *journal*, if the ranking file knows it."""
    key = text.normalize_title(journal)
    if not key:
        return None
    return _rankings().get(key)