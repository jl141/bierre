"""Unpaywall open-access enrichment (https://unpaywall.org).

Optional: requires a real contact email. When enabled, it fills in open-access
PDF links for papers that have a DOI. Disabled silently when no email is set.
"""

from __future__ import annotations

import re
from typing import Any

from ..util import text
from ..util.http import record_error, request_json
from ..models import Paper
from .base import SearchContext

API = "https://api.unpaywall.org/v2/{doi}"
# Supporting-information DOIs (…s001, …si) point at supplements, not the paper.
_SUPPLEMENT_SUFFIX = re.compile(r"(\.s\d{3}|\.si)$", re.I)


def _pdf_from(data: dict) -> str:
    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        return best["url_for_pdf"]
    for location in data.get("oa_locations", []) or []:
        if location.get("url_for_pdf"):
            return location["url_for_pdf"]
    return ""


def enrich(papers: list[Paper], ctx: SearchContext) -> None:
    """Fill open-access PDF links in place. No-op when no contact email."""
    if not ctx.email:
        record_error(
            ctx.errors,
            "unpaywall",
            "Unpaywall skipped: set contact_email to enable open-access PDF lookup.",
            "configuration_error",
        )
        return

    for paper in papers:
        doi = _SUPPLEMENT_SUFFIX.sub("", text.normalize_doi(paper.doi))
        if not doi:
            continue
        data: dict[str, Any] | None = request_json(
            API.format(doi=doi),
            {"email": ctx.email},
            ctx.timeout,
            ctx.errors,
            "unpaywall",
            **ctx.http_options("unpaywall"),
        )
        if not data:
            continue
        paper.oa_status = data.get("oa_status") or ("oa" if data.get("is_oa") else "closed")
        paper.pdf_url = _pdf_from(data) or paper.pdf_url
