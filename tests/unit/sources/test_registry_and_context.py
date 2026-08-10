"""Unit tests for the source registry, dispatch policies and `SearchContext`."""

from __future__ import annotations

import pytest

from core.config import ALL_SOURCES, Settings
from core.sources import REGISTRY, policy_for
from core.sources.base import SearchContext
from core.sources.policy import SourceDispatchState, allow_always, never_force_serial


def test_every_configurable_source_has_a_registered_adapter() -> None:
    assert set(REGISTRY) == set(ALL_SOURCES)
    assert all(callable(fn) for fn in REGISTRY.values())


def test_unknown_sources_get_the_permissive_default_policy() -> None:
    policy = policy_for("not-a-source")

    assert policy.allow_dispatch is allow_always
    assert policy.force_serial is never_force_serial


def test_the_default_policy_allows_concurrent_dispatch() -> None:
    policy = policy_for("openalex")
    settings, state = Settings(), SourceDispatchState()

    assert policy.allow_dispatch(settings, state) is True
    assert policy.force_serial(settings, state) is False


# --- dispatch state ----------------------------------------------------------


def test_dispatch_state_counts_per_source() -> None:
    state = SourceDispatchState()

    assert state.count("openalex") == 0
    state.increment("openalex")
    state.increment("openalex")

    assert state.count("openalex") == 2
    assert state.count("crossref") == 0


def test_consume_budget_stops_at_the_limit() -> None:
    state = SourceDispatchState()

    assert [state.consume_budget("s2", 2) for _ in range(3)] == [True, True, False]


def test_a_zero_or_negative_budget_never_allows_a_call() -> None:
    state = SourceDispatchState()

    assert state.consume_budget("s2", 0) is False
    assert state.consume_budget("s2", -5) is False


# --- context -----------------------------------------------------------------


def test_api_key_lookup_trims_and_defaults_to_empty() -> None:
    ctx = SearchContext(api_keys={"openalex": "  k1 ", "crossref": None})

    assert ctx.api_key("openalex") == "k1"
    assert ctx.api_key("crossref") == ""
    assert ctx.api_key("absent") == ""


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, {}),
        ({"other_stage": {"max_attempts": 9}}, {}),
        ({"crossref": {"max_attempts": 2, "nope": 1}}, {"max_attempts": 2}),
        (
            {
                "crossref": {
                    "max_attempts": 2,
                    "backoff_base_seconds": 0.25,
                    "backoff_max_seconds": 1.25,
                    "retryable_status_codes": [429],
                }
            },
            {
                "max_attempts": 2,
                "backoff_base_seconds": 0.25,
                "backoff_max_seconds": 1.25,
                "retryable_status_codes": [429],
            },
        ),
    ],
)
def test_http_options_only_passes_through_known_knobs(overrides, expected) -> None:
    """Unknown keys must be dropped: they would become invalid kwargs downstream."""
    ctx = SearchContext(http_overrides=overrides)

    assert ctx.http_options("crossref") == expected
