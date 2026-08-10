"""Fixtures shared by the search-source adapter tests."""

from __future__ import annotations

import pytest

from core.sources.base import SearchContext


@pytest.fixture
def ctx(errors: list[dict]) -> SearchContext:
    """A context wired to the test's error sink (the `errors` fixture)."""
    return SearchContext(max_results=3, timeout=10, email="", api_keys={}, errors=errors)


@pytest.fixture
def make_ctx(errors: list[dict]):
    """Build a context with overrides while keeping the shared error sink."""

    def build(**overrides) -> SearchContext:
        defaults = {"max_results": 3, "timeout": 10, "email": "", "api_keys": {}, "errors": errors}
        defaults.update(overrides)
        return SearchContext(**defaults)

    return build
