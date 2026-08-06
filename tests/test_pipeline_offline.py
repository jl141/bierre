"""Offline smoke tests — no network, exercise profile-driven behaviour.

Run with:  python -m pytest tests/   (or)   python tests/test_pipeline_offline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Settings, run_pipeline
from core.util.dedup import deduplicate
from core.models import Paper
from core.repositories.profile_repository import DomainProfile
from core.repositories.yaml_profile_repository import YamlProfileRepository


def _settings():
    return Settings.from_dict({"profile": "n-halamine"})

def test_offline_run_ranks_and_selects():
    result = run_pipeline("N-halamine rechargeable coating", _settings(), offline=True)
    assert result.mode == "offline"
    assert len(result.ranked) == 4
    assert result.selected, "expected at least one selected paper"
    # The strict N-halamine PU coating mock should outrank the off-topic silver one.
    titles = [r.paper.title for r in result.ranked]
    assert "polyurethane" in titles[0].lower()


def test_buckets_are_profile_driven():
    result = run_pipeline("N-halamine rechargeable coating", _settings(), offline=True)
    buckets = {r.paper.title[:18]: r.bucket for r in result.ranked}
    # Silver nanoparticle control has no N-halamine signal -> off-topic fallback.
    silver = next(r for r in result.ranked if "Silver" in r.paper.title)
    assert silver.bucket == "offtopic"
    core = next(r for r in result.ranked if "polyurethane" in r.paper.title.lower())
    assert core.bucket == "core"
    assert buckets  # sanity


def test_generic_profile_has_no_domain_bias():
    """The same off-topic paper is not penalised under the generic profile."""
    generic = DomainProfile.from_dict(YamlProfileRepository().get_profile("generic"))
    result = run_pipeline("silver nanoparticle hydrogel", _settings(), profile=generic, offline=True)
    for item in result.ranked:
        assert item.bucket == "all"          # only the fallback bucket exists
        assert item.off_topic_penalty == 0.0  # no off-topic list in generic


def test_dedup_merges_by_doi():
    papers = [
        Paper(title="A study", doi="10.1/x", abstract="short", sources=["OpenAlex"], search_queries=["q1"]),
        Paper(title="A study", doi="10.1/x", abstract="a much longer abstract", sources=["CrossRef"], search_queries=["q2"]),
    ]
    merged = deduplicate(papers)
    assert len(merged) == 1
    assert merged[0].abstract == "a much longer abstract"      # longest kept
    assert set(merged[0].sources) == {"OpenAlex", "CrossRef"}  # provenance merged
    assert merged[0].paper_id == "P0001"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All offline tests passed.")
