"""OpenAlex search adapter (https://openalex.org). Free, no key required."""

from __future__ import annotations

from ..util import text
from ..util.http import request_json
from ..models import Paper
from .base import SearchContext

URL = "https://api.openalex.org/works"


def _abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """OpenAlex returns abstracts as a word -> positions map; reassemble it."""
    if not inverted_index:
        return ""
    positioned = [(pos, word) for word, positions in inverted_index.items() for pos in positions]
    return " ".join(word for _, word in sorted(positioned))


def _authors(item: dict) -> str:
    names = [
        (auth.get("author") or {}).get("display_name", "")
        for auth in item.get("authorships", []) or []
    ]
    return "; ".join(n for n in names if n)


# TODO: journal-level impact proxy lives on the "source" (venue) object
# def _impact(item: dict) -> str:
#     primary_location = item.get("primary_location") or {}
#     source = primary_location.get("source")
#     if source and source.get("id"):
#         src_r = requests.get(source["id"], params={"mailto": "you@example.com"})
#         if src_r.ok:
#             src_data = src_r.json()
#             result["source_name"] = src_data.get("display_name")
#             # summary_stats.2yr_mean_citedness ~ analogous to journal impact factor
#             result["source_2yr_mean_citedness"] = (
#                 src_data.get("summary_stats", {}).get("2yr_mean_citedness")
#             )


def search(ctx: SearchContext, query: str) -> list[Paper]:
    params = {"search": query, "per-page": ctx.max_results}
    if ctx.email:
        params["mailto"] = ctx.email
    if ctx.api_key("openalex"):
        params["api_key"] = ctx.api_key("openalex")

    data = request_json(
        URL,
        params,
        ctx.timeout,
        ctx.errors,
        "openalex",
        **ctx.http_options("openalex"),
    )
    if not data:
        return []

    papers: list[Paper] = []
    for item in data.get("results", []) or []:
        location = item.get("primary_location") or {}
        best_oa = item.get("best_oa_location") or {}
        oa = item.get("open_access") or {}
        papers.append(
            Paper(
                title=item.get("title") or item.get("display_name") or "",
                authors=_authors(item),
                year=str(item.get("publication_year") or ""),
                journal=(location.get("source") or {}).get("display_name") or "",
                doi=text.normalize_doi(item.get("doi")),
                abstract=_abstract(item.get("abstract_inverted_index")),
                url=location.get("landing_page_url") or item.get("doi") or item.get("id") or "",
                pdf_url=location.get("pdf_url") or best_oa.get("pdf_url") or "",
                oa_status=oa.get("oa_status") or ("oa" if oa.get("is_oa") else ""),
                citation_count=item.get("cited_by_count"),
                sources=["OpenAlex"],
                search_queries=[query],
            )
        )
    return papers
