"""Structured data passed between pipeline stages.

The original workflow threaded loosely-typed ``dict`` records through every
stage. These dataclasses give each stage a clear contract and make the eventual
JSON/API boundary (Phase 2) a single ``to_dict`` call rather than ad-hoc key
juggling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import text


@dataclass
class Paper:
    """A single bibliographic record returned by one or more search sources."""

    title: str = ""
    authors: str = ""
    year: str = ""
    journal: str = ""
    doi: str = ""
    abstract: str = ""
    url: str = ""
    pdf_url: str = ""
    oa_status: str = ""
    citation_count: int | None = None
    influential_citation_count: int | None = None
    # Provenance: which source(s)/query(ies) produced this record (merged on dedup).
    sources: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    paper_id: str = ""

    def document_text(self) -> str:
        """Title-weighted text used for lexical ranking."""
        title = text.compact_whitespace(self.title)
        return text.compact_whitespace(f"{title} {title} {title} {self.abstract}")

    def classification_text(self) -> str:
        """All matchable text used for term/bucket classification."""
        parts = [self.title, self.abstract, self.journal, " ".join(self.search_queries)]
        return text.compact_whitespace(" ".join(parts))

    def evidence_text(self) -> str:
        """Best available free text for rule-based extraction."""
        return self.abstract or self.title


@dataclass
class RankedPaper:
    """A :class:`Paper` augmented with relevance scoring and selection state."""

    paper: Paper
    relevance: float = 0.0
    level: str = "Low"
    reasons: list[str] = field(default_factory=list)
    bucket: str = ""
    bucket_label: str = ""
    final_priority: float = 0.0
    off_topic_penalty: float = 0.0
    matched: dict[str, list[str]] = field(default_factory=dict)
    snippet: str = ""
    question_relevance: str = ""
    selected: bool = False
    rank: int = 0

    @property
    def status(self) -> str:
        return "Selected" if self.selected else "Not selected"

    def to_dict(self) -> dict[str, Any]:
        p = self.paper
        return {
            "paper_id": p.paper_id,
            "title": p.title,
            "authors": p.authors,
            "year": p.year,
            "journal": p.journal,
            "doi": p.doi,
            "url": p.url,
            "pdf_url": p.pdf_url,
            "sources": p.sources,
            "relevance_percent": round(self.relevance, 1),
            "level": self.level,
            "bucket": self.bucket_label or self.bucket,
            "final_priority": round(self.final_priority, 1),
            "selected": self.selected,
            "status": self.status,
            "rank": self.rank,
            "reason": "; ".join(self.reasons[:5]),
            "question_relevance": self.question_relevance,
            "snippet": self.snippet,
            "citation_count": p.citation_count,
            "influential_citation_count": p.influential_citation_count,
        }


@dataclass
class EvidenceRow:
    """Rule-based structured extraction for one selected paper."""

    paper_id: str
    title: str
    doi: str
    fields: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"paper_id": self.paper_id, "title": self.title, "doi": self.doi, **self.fields}


@dataclass
class RunResult:
    """Everything one pipeline run produces, ready to serialise."""

    run_id: str
    timestamp: str
    mode: str
    profile: str
    question: str
    queries: list[str] = field(default_factory=list)
    apis_used: list[str] = field(default_factory=list)
    ranked: list[RankedPaper] = field(default_factory=list)
    evidence: list[EvidenceRow] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def selected(self) -> list[RankedPaper]:
        return [r for r in self.ranked if r.selected]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "profile": self.profile,
            "question": self.question,
            "queries": self.queries,
            "apis_used": self.apis_used,
            "counts": {
                "found": len(self.ranked),
                "selected": len(self.selected),
            },
            "papers": [r.to_dict() for r in self.ranked],
            "evidence": [e.to_dict() for e in self.evidence],
            "errors": self.errors,
        }
