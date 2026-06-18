"""Search-source adapters. Each exposes ``search(ctx, query) -> list[Paper]``.

This is the only part of the core that performs network I/O.
"""

from __future__ import annotations

from .base import SearchContext
from . import crossref, europepmc, openalex, pubmed, semantic_scholar

# Registry mapping the config source name to its search callable.
REGISTRY = {
    "openalex": openalex.search,
    "crossref": crossref.search,
    "pubmed": pubmed.search,
    "europepmc": europepmc.search,
    "semantic_scholar": semantic_scholar.search,
}

__all__ = ["SearchContext", "REGISTRY"]
