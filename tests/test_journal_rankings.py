from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.util.journal_rankings import impact_factor_for_journal


def test_ooir_lookup_is_case_insensitive():
    assert impact_factor_for_journal("nature") == 56.1
    assert impact_factor_for_journal("Nature") == 56.1
    assert impact_factor_for_journal("") is None
