"""Builders for core domain objects.

Every builder takes keyword overrides, so a test states only the fields it
actually cares about. That keeps assertions readable and stops unrelated
schema changes from breaking dozens of tests at once.
"""

from __future__ import annotations

from typing import Any

from core.contracts.run_search import CONTRACT_VERSION, RunSearchResponse
from core.models import EvidenceRow, Paper, RankedPaper, RunResult
from core.repositories.profile_repository import Bucket, Concept, DomainProfile, ExtractionField

TIMESTAMP = "2026-08-06T00:00:00+00:00"


def make_paper(**overrides: Any) -> Paper:
    defaults: dict[str, Any] = {
        "title": "Sample paper",
        "authors": "Ada Lovelace",
        "year": "2026",
        "journal": "Test Journal",
        "doi": "10.1000/test",
        "abstract": "Sample abstract.",
        "sources": ["openalex"],
        "search_queries": ["sample query"],
        "paper_id": "P0001",
    }
    defaults.update(overrides)
    return Paper(**defaults)


def make_ranked_paper(paper: Paper | None = None, **overrides: Any) -> RankedPaper:
    defaults: dict[str, Any] = {
        "relevance": 88.2,
        "level": "High",
        "reasons": ["signal"],
        "bucket": "core",
        "bucket_label": "Core",
        "final_priority": 90.0,
        "selected": True,
        "rank": 1,
    }
    defaults.update(overrides)
    return RankedPaper(paper=paper or make_paper(), **defaults)


def make_evidence_row(**overrides: Any) -> EvidenceRow:
    defaults: dict[str, Any] = {
        "paper_id": "P0001",
        "title": "Sample paper",
        "doi": "10.1000/test",
        "fields": {"Methods": "Not reported"},
    }
    defaults.update(overrides)
    return EvidenceRow(**defaults)


def make_run_result(**overrides: Any) -> RunResult:
    defaults: dict[str, Any] = {
        "run_id": "run_123",
        "timestamp": TIMESTAMP,
        "mode": "offline",
        "profile": "generic",
        "question": "what is sample",
        "queries": ["sample query"],
        "apis_used": ["OfflineMock"],
        "ranked": [make_ranked_paper()],
        "evidence": [make_evidence_row()],
        "errors": [],
    }
    defaults.update(overrides)
    return RunResult(**defaults)


def make_response(**overrides: Any) -> RunSearchResponse:
    """A valid canonical response — the shape CLI and web must both emit."""
    defaults: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "request_id": "req_1",
        "run_id": "run_1",
        "timestamp": TIMESTAMP,
        "mode": "offline",
        "profile_id": "generic",
        "question": "q",
        "queries": ["q"],
        "apis_used": ["OfflineMock"],
        "scoring_summary": {
            "strategy": "hybrid",
            "selection_enabled": True,
            "selection_top_n": 10,
            "selection_min_relevance": 30.0,
        },
        "counts": {"found": 1, "selected": 1},
        "papers": [{"title": "T", "selected": True, "relevance_percent": 90.0, "bucket": "Core"}],
        "evidence": [{"paper_id": "P0001"}],
        "errors": [],
    }
    defaults.update(overrides)
    return RunSearchResponse(**defaults)


def make_profile(**overrides: Any) -> DomainProfile:
    """A small two-bucket profile with one concept — enough to drive ranking."""
    defaults: dict[str, Any] = {
        "name": "test-profile",
        "label": "Test Profile",
        "default_question": "default question about coatings",
        "concepts": [
            Concept(name="coating", triggers=["coating"], terms=["polyurethane coating", "epoxy coating"]),
        ],
        "query_groups": {"seed": ["coating durability", "coating adhesion"]},
        "off_topic_terms": ["silver nanoparticle"],
        "journal_terms": ["coatings"],
        "term_groups": {"chemistry": ["n-halamine", "active chlorine"], "substrate": ["polyurethane"]},
        "intents": {"coating": ["adhesion", "durability"]},
        "buckets": [
            Bucket(
                id="core",
                label="Core",
                boost=20.0,
                requires=["chemistry", "substrate"],
                exclude_off_topic=True,
            ),
            Bucket(id="adjacent", label="Adjacent", boost=5.0, requires=["chemistry"]),
            Bucket(id="other", label="Other", boost=0.0, fallback=True),
        ],
        "extraction_fields": [
            ExtractionField(name="Chemistry", terms=["n-halamine", "active chlorine"]),
            ExtractionField(name="Loading", terms=["active chlorine"], require_numeric=True),
        ],
    }
    defaults.update(overrides)
    return DomainProfile(**defaults)


def profile_payload(**overrides: Any) -> dict[str, Any]:
    """A repository-shaped (dict) profile payload, as stored in YAML."""
    payload: dict[str, Any] = {
        "label": "Hydrogel Search",
        "default_question": "q1",
        "concepts": [],
        "query_groups": {},
        "off_topic_terms": [],
        "journal_terms": [],
        "term_groups": {},
        "intents": {},
        "buckets": [{"id": "all", "label": "Relevant", "boost": 0.0, "fallback": True}],
        "extraction_fields": [],
    }
    payload.update(overrides)
    return payload
