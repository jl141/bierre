"""Merge duplicate papers returned by different sources/queries."""

from __future__ import annotations

from .util import text
from ..models import Paper


def _merge(into: Paper, other: Paper) -> None:
    """Fold ``other`` into ``into`` in place, preferring richer values."""
    for source in other.sources:
        if source not in into.sources:
            into.sources.append(source)
    for query in other.search_queries:
        if query not in into.search_queries:
            into.search_queries.append(query)
    # Keep the longest abstract; fill any blank scalar fields from the duplicate.
    if len(other.abstract) > len(into.abstract):
        into.abstract = other.abstract
    for attr in ("authors", "year", "journal", "doi", "url", "pdf_url", "oa_status"):
        if not getattr(into, attr) and getattr(other, attr):
            setattr(into, attr, getattr(other, attr))
    if into.citation_count is None and other.citation_count is not None:
        into.citation_count = other.citation_count
    if into.influential_citation_count is None and other.influential_citation_count is not None:
        into.influential_citation_count = other.influential_citation_count
    if into.impact_factor is None and other.impact_factor is not None:
        into.impact_factor = other.impact_factor


def deduplicate(papers: list[Paper]) -> list[Paper]:
    """Collapse papers sharing a DOI (or, failing that, a normalised title).

    Returns a new list in first-seen order, with stable ``paper_id`` values.
    """
    by_key: dict[str, Paper] = {}
    order: list[str] = []
    for paper in papers:
        doi = text.normalize_doi(paper.doi)
        title_key = text.normalize_title(paper.title)
        if doi:
            key = f"doi:{doi}"
        elif title_key:
            key = f"title:{title_key}"
        else:
            key = f"pos:{len(order)}"
        if key in by_key:
            _merge(by_key[key], paper)
        else:
            by_key[key] = paper
            order.append(key)

    deduped = [by_key[key] for key in order]
    for index, paper in enumerate(deduped, start=1):
        paper.paper_id = f"P{index:04d}"
    return deduped
