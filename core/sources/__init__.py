"""Search-source adapters. Each exposes ``search(ctx, query) -> list[Paper]``.

This is the only part of the core that performs network I/O.
"""

from __future__ import annotations

from .base import SearchContext
from . import crossref, europepmc, openalex, pubmed, semantic_scholar
from .policy import SourceDispatchState, SourcePolicy, allow_always, never_force_serial


DEFAULT_POLICY = SourcePolicy(allow_dispatch=allow_always, force_serial=never_force_serial)

# Registry mapping the config source name to its search callable.
REGISTRY = {
    "openalex": openalex.search,
    "crossref": crossref.search,
    "pubmed": pubmed.search,
    "europepmc": europepmc.search,
    "semantic_scholar": semantic_scholar.search,
}

# Optional per-source dispatch customization for planning search tasks.
POLICIES: dict[str, SourcePolicy] = {
    "crossref": SourcePolicy(
        allow_dispatch=allow_always,
        force_serial=crossref.force_serial,
    ),
    "pubmed": SourcePolicy(
        allow_dispatch=allow_always,
        force_serial=pubmed.force_serial,
    ),
    "semantic_scholar": SourcePolicy(
        allow_dispatch=semantic_scholar.allow_dispatch,
        force_serial=semantic_scholar.force_serial,
    )
}


def policy_for(source: str) -> SourcePolicy:
    return POLICIES.get(source, DEFAULT_POLICY)

__all__ = ["SearchContext", "REGISTRY", "SourceDispatchState", "SourcePolicy", "policy_for"]
