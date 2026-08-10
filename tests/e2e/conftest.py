"""Fixtures for end-to-end adapter tests (CLI and web entrypoints)."""

from __future__ import annotations

import pytest

from core.config import Settings
from core.contracts.run_search import RunSearchResponse
from tests.factories import make_response


class FakeSearchService:
    """A `SearchService` stand-in that returns one fixed canonical payload.

    Adapter tests care that the payload survives the transport unchanged, not
    how it was computed.
    """

    def __init__(self, _base_settings: Settings | None = None, **_kwargs) -> None:
        self.calls: list[object] = []

    def run(self, request, progress=None) -> RunSearchResponse:
        self.calls.append(request)
        if progress:
            progress(1, 1, "done")
        return make_response()


@pytest.fixture
def canonical_payload() -> dict:
    return make_response().to_dict()


@pytest.fixture
def fake_search_service() -> FakeSearchService:
    return FakeSearchService()
