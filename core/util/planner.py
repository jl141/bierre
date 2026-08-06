"""Turn a free-text research question into search queries (profile-driven).

The question is analysed into tokens, scientific names, phrases and active
concepts. Concepts and seed query groups come from the loaded
:class:`DomainProfile`, so the planner is general: the ``generic`` profile
produces purely question-derived queries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import text
from ..profiles import DomainProfile

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "can",
    "could", "for", "from", "how", "in", "into", "is", "may", "of", "on", "or",
    "should", "the", "to", "using", "with", "what", "which", "that", "while",
}
_FALSE_NAME_STARTS = {"How", "What", "When", "Where", "Why", "Which", "Please"}


@dataclass
class QuestionAnalysis:
    question: str
    keywords: list[str] = field(default_factory=list)
    scientific_names: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    expanded_terms: list[str] = field(default_factory=list)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = text.compact_whitespace(value).strip(" ,.;:")
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def _keywords(question: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+/-]{1,}", question)
    tokens = [t.strip(" .,+/-").lower() for t in raw]
    return _unique([t for t in tokens if len(t) >= 3 and t not in _STOPWORDS])


def _scientific_names(question: str) -> list[str]:
    full = re.findall(r"\b[A-Z][a-z]+ [a-z]{3,}\b", question)
    abbreviations = re.findall(r"\b[A-Z]\. ?[a-z]{3,}\b", question)
    full = [name for name in full if name.split()[0] not in _FALSE_NAME_STARTS]
    return _unique(full + abbreviations)


def analyze_question(question: str, profile: DomainProfile) -> QuestionAnalysis:
    """Extract keywords, names and profile concepts active in the question."""
    question = text.compact_whitespace(question)
    lower = question.lower()
    concepts: list[str] = []
    expanded: list[str] = []
    for concept in profile.concepts:
        if any(trigger.lower() in lower for trigger in concept.triggers):
            concepts.append(concept.name)
            expanded.extend(concept.terms)
    return QuestionAnalysis(
        question=question,
        keywords=_keywords(question),
        scientific_names=_scientific_names(question),
        concepts=_unique(concepts),
        expanded_terms=_unique(expanded),
    )


def generate_queries(question: str, profile: DomainProfile) -> list[str]:
    """Build the list of search strings to run for ``question``.

    Always includes the raw question plus a keyword-derived query. If any
    profile concept is active, the profile's curated seed query groups are
    appended (this is what makes a domain profile worth loading).
    """
    analysis = analyze_question(question, profile)
    queries: list[str] = [analysis.question]

    head_terms = (analysis.scientific_names + analysis.keywords)[:6]
    if head_terms:
        queries.append(" ".join(head_terms))
    if analysis.expanded_terms:
        queries.append(" ".join(analysis.expanded_terms[:6]))

    if analysis.concepts:
        for group in profile.query_groups.values():
            queries.extend(group)

    return _unique([q for q in queries if q])
