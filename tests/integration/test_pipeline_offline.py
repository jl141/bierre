"""Offline pipeline runs: planner -> mock sources -> dedup -> ranking -> extraction.

`offline=True` swaps the network sources for built-in fixtures, so the whole
orchestration is exercised without touching an API.
"""

from __future__ import annotations

from core import Settings, run_pipeline
from core.repositories.profile_repository import DomainProfile
from core.repositories.yaml_profile_repository import YamlProfileRepository
from tests.conftest import REAL_PROFILES_DIR


def _settings(**overrides) -> Settings:
    return Settings.from_dict({"profile": "n-halamine", **overrides})


def _profile(name: str) -> DomainProfile:
    return DomainProfile.from_dict(YamlProfileRepository(REAL_PROFILES_DIR).get_profile(name))


def test_an_offline_run_ranks_and_selects_the_mock_corpus() -> None:
    result = run_pipeline("N-halamine rechargeable coating", _settings(), offline=True)

    assert result.mode == "offline"
    assert result.apis_used == ["OfflineMock"]
    assert len(result.ranked) == 4
    assert result.selected
    assert "polyurethane" in result.ranked[0].paper.title.lower()


def test_buckets_come_from_the_profile_not_the_code() -> None:
    result = run_pipeline("N-halamine rechargeable coating", _settings(), offline=True)

    silver = next(item for item in result.ranked if "Silver" in item.paper.title)
    core = next(item for item in result.ranked if "polyurethane" in item.paper.title.lower())

    assert silver.bucket == "offtopic"
    assert core.bucket == "core"


def test_the_generic_profile_applies_no_domain_bias() -> None:
    result = run_pipeline(
        "silver nanoparticle hydrogel", _settings(), profile=_profile("generic"), offline=True
    )

    for item in result.ranked:
        assert item.bucket == "all"
        assert item.off_topic_penalty == 0.0


def test_an_empty_question_falls_back_to_the_profile_default() -> None:
    profile = _profile("n-halamine")

    result = run_pipeline("   ", _settings(), profile=profile, offline=True)

    assert result.question == profile.default_question


def test_the_run_result_is_json_serialisable_and_self_consistent() -> None:
    payload = run_pipeline("N-halamine coating", _settings(), offline=True).to_dict()

    assert payload["counts"]["found"] == len(payload["papers"])
    assert payload["counts"]["selected"] == sum(1 for p in payload["papers"] if p["selected"])
    assert len(payload["evidence"]) == payload["counts"]["selected"]
    assert payload["run_id"].startswith("run_")


def test_every_selected_paper_gets_the_profile_extraction_columns() -> None:
    profile = _profile("n-halamine")
    result = run_pipeline("N-halamine coating", _settings(), profile=profile, offline=True)

    expected_columns = {field.name for field in profile.extraction_fields}
    for row in result.evidence:
        assert set(row.fields) == expected_columns


def test_progress_is_reported_monotonically_to_the_callback() -> None:
    steps: list[tuple[int, int, str]] = []

    run_pipeline("N-halamine coating", _settings(), offline=True, progress=lambda *args: steps.append(args))

    assert steps[0][0] == 1
    assert steps[-1] == (4, 4, "Done")
    assert [step for step, _total, _label in steps] == sorted(step for step, _t, _l in steps)


def test_queries_are_capped_by_max_queries_per_run() -> None:
    result = run_pipeline(
        "N-halamine rechargeable coating", _settings(search={"max_queries_per_run": 2}), offline=True
    )

    assert len(result.queries) == 2


def test_selection_can_be_disabled_so_every_paper_is_extracted() -> None:
    result = run_pipeline(
        "N-halamine coating", _settings(selection={"enabled": False}), offline=True
    )

    assert len(result.selected) == len(result.ranked) == 4


def test_unpaywall_never_runs_in_offline_mode() -> None:
    """Offline must stay strictly network-free even with enrichment enabled."""
    result = run_pipeline(
        "N-halamine coating",
        _settings(use_unpaywall=True, contact_email="me@example.org"),
        offline=True,
    )

    assert "unpaywall" not in result.apis_used
    assert result.errors == []
