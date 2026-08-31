"""Europe PMC search adapter (https://europepmc.org). Free, life-sciences focus."""

from __future__ import annotations

from typing import Any

from ..utils import text
from ..utils.http import request_json
from ..models import Paper
from .base import SearchContext

URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _article_url(item: dict) -> str:
    source, article_id = str(item.get("source") or ""), str(item.get("id") or "")
    if source and article_id:
        return f"https://europepmc.org/article/{source}/{article_id}"
    doi = text.normalize_doi(item.get("doi"))
    return f"https://doi.org/{doi}" if doi else ""


def _pdf_url(item: dict) -> str:
    for url_item in (item.get("fullTextUrlList") or {}).get("fullTextUrl", []) or []:
        style = str(url_item.get("documentStyle") or "").lower()
        availability = str(url_item.get("availability") or "").lower()
        if "pdf" in style and ("open" in availability or "free" in availability):
            return str(url_item.get("url") or "")
    return ""


def search(ctx: SearchContext, query: str) -> list[Paper]:
    params: dict[str, Any] = {
        "query": query,
        "format": "json",
        "pageSize": ctx.max_results,
        "resultType": "core",
    }
    data = request_json(
        URL,
        params,
        ctx.timeout,
        ctx.errors,
        "europepmc",
        **ctx.http_options("europepmc"),
    )
    if not data:
        return []

    papers: list[Paper] = []
    for item in ((data.get("resultList") or {}).get("result", []) or []):
        papers.append(
            Paper(
                title=text.strip_markup(item.get("title", "")),
                authors=text.strip_markup(item.get("authorString", "")),
                year=str(item.get("pubYear") or item.get("firstPublicationDate") or ""),
                journal=text.strip_markup(item.get("journalTitle", "")),
                doi=text.normalize_doi(item.get("doi")),
                abstract=text.strip_markup(item.get("abstractText", "")),
                url=_article_url(item),
                pdf_url=_pdf_url(item),
                oa_status=str(item.get("isOpenAccess") or ""),
                sources=["EuropePMC"],
                search_queries=[query],
            )
        )
    return papers
