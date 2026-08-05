"""CrossRef search adapter (https://crossref.org). Free; ``mailto`` = polite pool."""

from __future__ import annotations

from typing import Any

from ..config import Settings
from .. import text
from ..http import request_json
from ..models import Paper
from .base import SearchContext
from .policy import SourceDispatchState

URL = "https://api.crossref.org/works"


def force_serial(settings: Settings, state: SourceDispatchState) -> bool:
    """CrossRef public pools throttle aggressively; query serially."""
    del settings, state
    return True


def _first(value: Any) -> str:
    return str(value[0]) if isinstance(value, list) and value else ""


def _authors(item: dict) -> str:
    names = []
    for author in item.get("author", []) or []:
        name = " ".join(p for p in [author.get("given", ""), author.get("family", "")] if p).strip()
        if name:
            names.append(name)
    return "; ".join(names)


def _year(item: dict) -> str:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts", [])
        if parts and parts[0]:
            return str(parts[0][0])
    return ""


def search(ctx: SearchContext, query: str) -> list[Paper]:
    params: dict[str, Any] = {"query.bibliographic": query, "rows": ctx.max_results}
    if ctx.email:
        params["mailto"] = ctx.email

    data = request_json(
        URL,
        params,
        ctx.timeout,
        ctx.errors,
        "crossref",
        **ctx.http_options("crossref"),
    )
    if not data:
        return []

    papers: list[Paper] = []
    for item in (data.get("message") or {}).get("items", []) or []:
        papers.append(
            Paper(
                title=text.strip_markup(_first(item.get("title"))),
                authors=_authors(item),
                year=_year(item),
                journal=text.strip_markup(_first(item.get("container-title"))),
                doi=text.normalize_doi(item.get("DOI")),
                abstract=text.strip_markup(item.get("abstract", "")),
                url=item.get("URL", ""),
                sources=["CrossRef"],
                search_queries=[query],
            )
        )
    return papers
