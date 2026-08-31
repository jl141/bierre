"""Semantic Scholar search adapter. Free; a key improves reliability/limits.

Also supplies citation counts, which feed the ranking quality signal.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..utils import text
from ..utils.http import record_error, request_json
from ..models import Paper
from .base import SearchContext
from .policy import SourceDispatchState

URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,authors,year,venue,externalIds,abstract,url,openAccessPdf,citationCount,influentialCitationCount"


def allow_dispatch(settings: Settings, state: SourceDispatchState) -> bool:
    """Gate anonymous calls through a shared per-run source budget."""
    if settings.api_key("semantic_scholar"):
        return True
    return state.consume_budget("semantic_scholar", settings.search.semantic_scholar_max_queries_without_key)


def force_serial(settings: Settings, state: SourceDispatchState) -> bool:
    """Anonymous traffic is queried serially to reduce throttling."""
    del state
    return not bool(settings.api_key("semantic_scholar"))


def _authors(item: dict) -> str:
    return "; ".join(text.compact_whitespace(a.get("name", "")) for a in item.get("authors", []) or [] if a.get("name"))


def _parse(data: dict, query: str) -> list[Paper]:
    papers: list[Paper] = []
    for item in (data or {}).get("data", []) or []:
        external = item.get("externalIds") or {}
        pdf = (item.get("openAccessPdf") or {}).get("url", "")
        papers.append(
            Paper(
                title=text.strip_markup(item.get("title", "")),
                authors=_authors(item),
                year=str(item.get("year") or ""),
                journal=text.strip_markup(item.get("venue", "")),
                doi=text.normalize_doi(external.get("DOI")),
                abstract=text.strip_markup(item.get("abstract", "")),
                url=item.get("url") or "",
                pdf_url=text.compact_whitespace(pdf),
                oa_status="open_pdf" if pdf else "",
                citation_count=item.get("citationCount"),
                influential_citation_count=item.get("influentialCitationCount"),
                sources=["SemanticScholar"],
                search_queries=[query],
            )
        )
    return papers


def search(ctx: SearchContext, query: str) -> list[Paper]:
    params: dict[str, Any] = {"query": query, "limit": min(ctx.max_results, 100), "fields": FIELDS}
    headers: dict[str, str] = {}
    if ctx.api_key("semantic_scholar"):
        headers["X-API-KEY"] = ctx.api_key("semantic_scholar")

    data = request_json(
        URL,
        params,
        ctx.timeout,
        ctx.errors,
        "semantic_scholar",
        headers=headers,
        **ctx.http_options("semantic_scholar"),
    )
    if not isinstance(data, dict):
        return []
    try:
        return _parse(data, query)
    except (TypeError, ValueError) as exc:
        # Keep adapter-level parse protection if the remote payload shape drifts.
        record_error(ctx.errors, "semantic_scholar", str(exc), "json_parse_error")
    return []
