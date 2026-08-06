from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Settings
from core.contracts.run_search import (
    CONTRACT_VERSION,
    RunSearchRequest,
    RunSearchResponse,
    map_run_result_to_response,
)
from core.models import EvidenceRow, Paper, RankedPaper, RunResult


def _sample_run_result() -> RunResult:
    paper = Paper(
        title="Sample paper",
        authors="Ada",
        year="2026",
        journal="Test Journal",
        doi="10.1000/test",
        abstract="Sample abstract",
        sources=["openalex"],
        search_queries=["sample query"],
        paper_id="P0001",
    )
    ranked = RankedPaper(
        paper=paper,
        relevance=88.2,
        level="High",
        reasons=["signal"],
        bucket="core",
        bucket_label="Core",
        final_priority=90.0,
        selected=True,
        rank=1,
    )
    evidence = EvidenceRow(paper_id="P0001", title="Sample paper", doi="10.1000/test", fields={"k": "v"})
    return RunResult(
        run_id="run_123",
        timestamp="2026-08-06T00:00:00+00:00",
        mode="offline",
        profile="generic",
        question="what is sample",
        queries=["sample query"],
        apis_used=["OfflineMock"],
        ranked=[ranked],
        evidence=[evidence],
        errors=[],
    )


def test_run_search_request_requires_question() -> None:
    try:
        RunSearchRequest(question="")
    except ValueError as exc:
        assert "question is required" in str(exc)
    else:
        raise AssertionError("Expected question validation error")


def test_run_search_request_from_dict_defaults_contract_version() -> None:
    request = RunSearchRequest.from_dict({"question": "q1"})
    assert request.contract_version == CONTRACT_VERSION
    assert request.question == "q1"


def test_run_search_response_requires_scoring_summary_keys() -> None:
    try:
        RunSearchResponse(
            contract_version=CONTRACT_VERSION,
            request_id="req_1",
            run_id="run_1",
            timestamp="2026-08-06T00:00:00+00:00",
            mode="online",
            profile_id="generic",
            question="q",
            scoring_summary={},
            counts={"found": 0, "selected": 0},
        )
    except ValueError as exc:
        assert "scoring_summary missing keys" in str(exc)
    else:
        raise AssertionError("Expected scoring_summary validation error")


def test_map_run_result_to_response_emits_canonical_shape() -> None:
    result = _sample_run_result()
    settings = Settings.from_dict({"selection": {"enabled": True, "top_n": 5, "min_relevance": 42.0}})

    response = map_run_result_to_response(result, request_id="req_abc", settings=settings)
    payload = response.to_dict()

    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["request_id"] == "req_abc"
    assert payload["counts"] == {"found": 1, "selected": 1}
    assert payload["scoring_summary"]["strategy"] == "hybrid"
    assert payload["scoring_summary"]["selection_top_n"] == 5
    assert payload["papers"][0]["title"] == "Sample paper"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All contract tests passed.")
