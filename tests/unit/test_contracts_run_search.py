"""Unit tests for `core.contracts.run_search` — the cross-adapter wire contract.

Every rule here is a promise to clients (CLI, web UI, future API). Loosening one
of these tests means breaking that promise, so add a new contract version
instead.
"""

from __future__ import annotations

import pytest

from core.config import Settings
from core.contracts.run_search import (
    CONTRACT_VERSION,
    RunSearchRequest,
    RunSearchResponse,
    map_run_result_to_response,
)
from tests.factories import make_response, make_run_result


# --- request ---------------------------------------------------------------


def test_request_requires_a_question() -> None:
    with pytest.raises(ValueError, match="question is required"):
        RunSearchRequest(question="   ")


def test_request_trims_and_defaults_the_contract_version() -> None:
    request = RunSearchRequest.from_dict({"question": "  q1  ", "profile_id": " generic "})

    assert request.contract_version == CONTRACT_VERSION
    assert request.question == "q1"
    assert request.profile_id == "generic"


def test_request_rejects_an_unknown_contract_version() -> None:
    with pytest.raises(ValueError, match="Unsupported contract_version"):
        RunSearchRequest(contract_version="v99", question="q")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"settings_overrides": []}, "settings_overrides must be an object"),
        ({"requested_outputs": "json"}, "requested_outputs must be a list"),
        ({"requested_outputs": [""]}, "requested_outputs must be a list"),
        ({"requested_outputs": [1]}, "requested_outputs must be a list"),
    ],
)
def test_request_rejects_malformed_optional_fields(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        RunSearchRequest(question="q", **kwargs)


def test_request_from_dict_rejects_a_non_object_payload() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        RunSearchRequest.from_dict(["q"])  # type: ignore[arg-type]


def test_request_round_trips_through_to_dict() -> None:
    request = RunSearchRequest(question="q", profile_id="generic", offline=True, request_id="req_1")

    assert RunSearchRequest.from_dict(request.to_dict()).to_dict() == request.to_dict()


# --- response --------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"request_id": ""}, "request_id is required"),
        ({"run_id": ""}, "run_id is required"),
        ({"timestamp": ""}, "timestamp is required"),
        ({"mode": "dry-run"}, "mode must be 'offline' or 'online'"),
        ({"profile_id": ""}, "profile_id is required"),
        ({"question": ""}, "question is required"),
        ({"scoring_summary": {}}, "scoring_summary missing keys"),
        ({"scoring_summary": []}, "scoring_summary must be an object"),
        ({"counts": {"found": 1}}, "counts must include found and selected"),
        ({"counts": []}, "counts must be an object"),
    ],
)
def test_response_validates_every_required_field(overrides, message) -> None:
    with pytest.raises(ValueError, match=message):
        make_response(**overrides)


def test_response_to_dict_key_set_is_frozen_for_v1() -> None:
    assert set(make_response().to_dict()) == {
        "contract_version",
        "request_id",
        "run_id",
        "timestamp",
        "mode",
        "profile_id",
        "question",
        "queries",
        "apis_used",
        "scoring_summary",
        "counts",
        "papers",
        "evidence",
        "errors",
    }


def test_response_to_dict_copies_mutable_collections() -> None:
    response = make_response()
    payload = response.to_dict()

    payload["queries"].append("mutated")
    payload["scoring_summary"]["strategy"] = "mutated"

    assert response.queries == ["q"]
    assert response.scoring_summary["strategy"] == "hybrid"


# --- mapping ---------------------------------------------------------------


def test_map_run_result_emits_the_canonical_shape() -> None:
    settings = Settings.from_dict({"selection": {"enabled": True, "top_n": 5, "min_relevance": 42.0}})

    payload = map_run_result_to_response(
        make_run_result(), request_id="req_abc", settings=settings
    ).to_dict()

    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["request_id"] == "req_abc"
    assert payload["counts"] == {"found": 1, "selected": 1}
    assert payload["scoring_summary"] == {
        "strategy": "hybrid",
        "selection_enabled": True,
        "selection_top_n": 5,
        "selection_min_relevance": 42.0,
    }
    assert payload["papers"][0]["title"] == "Sample paper"
    assert payload["evidence"][0]["paper_id"] == "P0001"


def test_map_run_result_reports_the_internal_profile_name_as_profile_id() -> None:
    response = map_run_result_to_response(
        make_run_result(profile="n-halamine"), request_id="req_1", settings=Settings()
    )

    assert response.profile_id == "n-halamine"


def test_scoring_strategy_is_fixed_for_v1_regardless_of_internals() -> None:
    response = map_run_result_to_response(make_run_result(), request_id="req_1", settings=Settings())

    assert response.scoring_summary["strategy"] == "hybrid"


def test_response_type_is_a_valid_runsearchresponse() -> None:
    response = map_run_result_to_response(make_run_result(), request_id="req_1", settings=Settings())

    assert isinstance(response, RunSearchResponse)
