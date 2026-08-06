"""Canonical contract models exposed at adapter boundaries."""

from .run_search import (
    CONTRACT_VERSION,
    RunSearchRequest,
    RunSearchResponse,
    map_run_result_to_response,
)

__all__ = [
    "CONTRACT_VERSION",
    "RunSearchRequest",
    "RunSearchResponse",
    "map_run_result_to_response",
]
