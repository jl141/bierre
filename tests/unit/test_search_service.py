"""Unit tests for `SearchService` — request -> settings merge -> pipeline -> contract.

`SearchService` takes its profile loader and pipeline runner as injectable
callables, so these tests never touch the filesystem or the network.
"""

from __future__ import annotations

import pytest

from core.config import Settings
from core.contracts.run_search import RunSearchRequest
from core.repositories.profile_repository import DomainProfile
from core.services.search_service import SearchService
from tests.factories import make_run_result


@pytest.fixture
def recorder():
    """A pipeline runner double that records the arguments it was called with."""
    calls: dict = {}

    def runner(*, question, settings, profile, offline, progress):
        calls.update(
            question=question,
            settings=settings,
            profile_name=profile.name,
            offline=offline,
            progress=progress,
        )
        return make_run_result(
            mode="offline" if offline else "online", profile=profile.name, question=question
        )

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def _service(recorder, settings: Settings | None = None, **kwargs) -> SearchService:
    return SearchService(
        base_settings=settings or Settings.from_dict({"profile": "generic", "selection": {"top_n": 25}}),
        profile_loader=lambda profile_id: DomainProfile(name=profile_id, label=profile_id),
        pipeline_runner=recorder,
        **kwargs,
    )


# --- run() -------------------------------------------------------------------


def test_run_passes_the_request_through_to_the_pipeline(recorder) -> None:
    response = _service(recorder).run(
        RunSearchRequest(question="hello", profile_id="n-halamine", offline=True, request_id="req_1")
    )

    assert recorder.calls["question"] == "hello"
    assert recorder.calls["profile_name"] == "n-halamine"
    assert recorder.calls["offline"] is True
    assert response.request_id == "req_1"
    assert response.profile_id == "n-halamine"


def test_an_absent_profile_id_falls_back_to_the_configured_profile(recorder) -> None:
    _service(recorder).run(RunSearchRequest(question="hello"))

    assert recorder.calls["profile_name"] == "generic"


def test_a_missing_request_id_is_generated(recorder) -> None:
    response = _service(recorder).run(RunSearchRequest(question="hello"))

    assert response.request_id.startswith("req_")
    assert len(response.request_id) > len("req_")


def test_the_progress_callback_is_forwarded(recorder) -> None:
    def progress(step, total, label):
        return None

    _service(recorder).run(RunSearchRequest(question="hello"), progress=progress)

    assert recorder.calls["progress"] is progress


def test_the_response_reports_the_merged_selection_settings(recorder) -> None:
    response = _service(recorder).run(
        RunSearchRequest(question="hello", settings_overrides={"selection": {"top_n": 7}})
    )

    assert recorder.calls["settings"].selection.top_n == 7
    assert response.scoring_summary["selection_top_n"] == 7


# --- settings merge ----------------------------------------------------------


def test_no_overrides_reuses_the_base_settings_object(recorder) -> None:
    base = Settings.from_dict({"profile": "generic"})

    _service(recorder, settings=base).run(RunSearchRequest(question="hello"))

    assert recorder.calls["settings"] is base


def test_a_non_dict_override_payload_is_rejected(recorder) -> None:
    with pytest.raises(ValueError, match="settings_overrides must be an object"):
        SearchService._merge_settings(Settings(), ["not-a-dict"])  # type: ignore[arg-type]


def test_client_overrides_may_only_tighten_search_and_selection_limits() -> None:
    """Guard rail: a client can ask for *less* work, never more.

    `_safe_update` applies an override only when it is strictly lower than the
    server-side value, so a client cannot raise `top_n` or `timeout_seconds`.
    """
    base = Settings.from_dict({"selection": {"top_n": 25}, "search": {"timeout_seconds": 20}})

    tightened = SearchService._merge_settings(base, {"selection": {"top_n": 5}, "search": {"timeout_seconds": 5}})
    widened = SearchService._merge_settings(base, {"selection": {"top_n": 500}})

    assert tightened.selection.top_n == 5
    assert tightened.search.timeout_seconds == 5
    assert widened.selection.top_n == 25  # silently ignored, not an error


def test_overrides_outside_the_allow_list_are_dropped() -> None:
    base = Settings.from_dict({"search": {"semantic_scholar_max_queries_without_key": 3}})

    merged = SearchService._merge_settings(base, {"search": {"semantic_scholar_max_queries_without_key": 0}})

    assert merged.search.semantic_scholar_max_queries_without_key == 3


def test_api_keys_are_merged_rather_than_replaced() -> None:
    base = Settings.from_dict({"api_keys": {"openalex": "a", "semantic_scholar": "b"}})

    merged = SearchService._merge_settings(base, {"api_keys": {"semantic_scholar": "c"}})

    assert merged.api_keys == {"openalex": "a", "semantic_scholar": "c"}


def test_top_level_keys_are_replaced_outright() -> None:
    merged = SearchService._merge_settings(Settings(), {"profile": "n-halamine", "use_unpaywall": True})

    assert merged.profile == "n-halamine"
    assert merged.use_unpaywall is True


def test_a_wrongly_typed_limit_override_raises() -> None:
    """Known sharp edge: the clamp compares with `<`, so a string raises TypeError.

    Adapters must validate types before calling (the web layer's pydantic model
    is what currently keeps this out of production).
    """
    with pytest.raises(TypeError):
        SearchService._merge_settings(Settings(), {"selection": {"top_n": "lots"}})
