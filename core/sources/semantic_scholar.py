"""Semantic Scholar search adapter. Free; a key improves reliability/limits.

Also supplies citation counts, which feed the ranking quality signal.
"""

from __future__ import annotations

from typing import Any

import requests

from .. import text
from ..http import USER_AGENT, record_error
from ..models import Paper
from .base import SearchContext

URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,authors,year,venue,externalIds,abstract,url,openAccessPdf,citationCount,influentialCitationCount"


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
    headers = {"User-Agent": USER_AGENT}
    if ctx.api_key("semantic_scholar"):
        headers["x-api-key"] = ctx.api_key("semantic_scholar")
    try:
        resp = requests.get(URL, params=params, timeout=ctx.timeout, headers=headers)
        resp.raise_for_status()
        return _parse(resp.json(), query)
    except (requests.RequestException, ValueError) as exc:
        record_error(ctx.errors, "semantic_scholar", str(exc), "network_or_api_error")
    return []
