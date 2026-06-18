"""PubMed search adapter via NCBI E-utilities. Free; an NCBI key raises limits.

Two calls: ``esearch`` returns PMIDs for the query, then ``efetch`` returns the
article XML we parse into :class:`Paper` records.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import requests

from .. import text
from ..http import USER_AGENT, record_error
from ..models import Paper
from .base import SearchContext

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _text(element: ET.Element | None) -> str:
    return text.compact_whitespace(" ".join(element.itertext())) if element is not None else ""


def _authors(article: ET.Element) -> str:
    names = []
    for author in article.findall(".//AuthorList/Author"):
        collective = _text(author.find("CollectiveName"))
        if collective:
            names.append(collective)
            continue
        last = _text(author.find("LastName"))
        fore = _text(author.find("ForeName")) or _text(author.find("Initials"))
        name = " ".join(p for p in [fore, last] if p)
        if name:
            names.append(name)
    return "; ".join(names)


def _year(article: ET.Element) -> str:
    for path in (".//ArticleDate/Year", ".//JournalIssue/PubDate/Year", ".//PubDate/Year"):
        value = _text(article.find(path))
        if value:
            return value
    match = re.search(r"\b(19|20)\d{2}\b", _text(article.find(".//PubDate/MedlineDate")))
    return match.group(0) if match else ""


def _doi(article: ET.Element) -> str:
    for article_id in article.findall(".//ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType", "").lower() == "doi":
            return text.normalize_doi(_text(article_id))
    return ""


def _parse(xml_text: str, query: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _text(article.find(".//PMID"))
        abstract_parts = [_text(n) for n in article.findall(".//Abstract/AbstractText")]
        papers.append(
            Paper(
                title=text.strip_markup(_text(article.find(".//ArticleTitle"))),
                authors=_authors(article),
                year=_year(article),
                journal=text.strip_markup(_text(article.find(".//Journal/Title"))),
                doi=_doi(article),
                abstract=text.strip_markup(" ".join(p for p in abstract_parts if p)),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                sources=["PubMed"],
                search_queries=[query],
            )
        )
    return papers


def search(ctx: SearchContext, query: str) -> list[Paper]:
    common: dict[str, Any] = {"db": "pubmed", "tool": "bierre"}
    if ctx.email:
        common["email"] = ctx.email
    if ctx.api_key("ncbi"):
        common["api_key"] = ctx.api_key("ncbi")
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(
            ESEARCH,
            params={**common, "term": query, "retmax": ctx.max_results, "retmode": "json"},
            timeout=ctx.timeout,
            headers=headers,
        )
        resp.raise_for_status()
        ids = (resp.json().get("esearchresult") or {}).get("idlist", [])
    except (requests.RequestException, ValueError) as exc:
        record_error(ctx.errors, "pubmed_esearch", str(exc), "network_or_api_error")
        return []

    if not ids:
        return []

    try:
        resp = requests.get(
            EFETCH,
            params={**common, "id": ",".join(ids), "retmode": "xml"},
            timeout=ctx.timeout,
            headers=headers,
        )
        resp.raise_for_status()
        return _parse(resp.text, query)
    except requests.RequestException as exc:
        record_error(ctx.errors, "pubmed_efetch", str(exc), "network_or_api_error")
    except ET.ParseError as exc:
        record_error(ctx.errors, "pubmed_efetch", str(exc), "xml_parse_error")
    return []
