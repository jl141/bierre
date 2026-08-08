from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Settings
from core.contracts.run_search import RunSearchRequest
from core.models import RunResult
from core.repositories.profile_repository import DomainProfile
from core.repositories.profile_repository import ProfileSummary
from core.services.profile_service import ProfileService
from core.services.search_service import SearchService


class FakeProfileRepository:
    def __init__(self) -> None:
        self.created_payload = None
        self.updated_payload = None
        self.deleted_profile_id = None

    def list_profiles(self) -> list[ProfileSummary]:
        return [
            ProfileSummary(
                profile_id="generic",
                label="Generic",
                created_at="2026-08-06T00:00:00+00:00",
                updated_at="2026-08-06T00:00:00+00:00",
                is_builtin=True,
            )
        ]

    def get_profile(self, profile_id: str) -> dict:
        return {"name": profile_id, "label": "Profile"}

    def create_profile(self, payload: dict) -> dict:
        self.created_payload = payload
        return {"id": "new-profile", "profile": payload}

    def update_profile(self, profile_id: str, payload: dict) -> dict:
        self.updated_payload = (profile_id, payload)
        return {"id": profile_id, "profile": payload}

    def delete_profile(self, profile_id: str) -> None:
        self.deleted_profile_id = profile_id


def test_profile_service_delegates_repository_calls() -> None:
    repo = FakeProfileRepository()
    service = ProfileService(repository=repo)

    listed = service.list_profiles()
    fetched = service.get_profile("generic")
    created = service.create_profile({"label": "X"})
    updated = service.update_profile("generic", {"label": "Y"})
    service.delete_profile("generic")

    assert listed[0].profile_id == "generic"
    assert fetched["name"] == "generic"
    assert created["id"] == "new-profile"
    assert updated["id"] == "generic"
    assert repo.created_payload == {"label": "X"}
    assert repo.updated_payload == ("generic", {"label": "Y"})
    assert repo.deleted_profile_id == "generic"


def test_search_service_runs_pipeline_and_maps_response() -> None:
    called = {}

    def fake_profile_loader(name: str) -> DomainProfile:
        called["profile_loader"] = name
        return DomainProfile(name=name, label=name, default_question="dq")

    def fake_pipeline_runner(*, question, settings, profile, offline, progress):
        called["question"] = question
        called["profile_name"] = profile.name
        called["offline"] = offline
        called["selection_top_n"] = settings.selection.top_n
        return RunResult(
            run_id="run_x",
            timestamp="2026-08-06T00:00:00+00:00",
            mode="offline" if offline else "online",
            profile=profile.name,
            question=question,
            queries=["q"],
            apis_used=["OfflineMock"],
            ranked=[],
            evidence=[],
            errors=[],
        )

    service = SearchService(
        base_settings=Settings.from_dict({"profile": "generic", "selection": {"top_n": 25}}),
        profile_loader=fake_profile_loader,
        pipeline_runner=fake_pipeline_runner,
    )

    response = service.run(
        RunSearchRequest(
            question="hello",
            profile_id="n-halamine",
            offline=True,
            request_id="req_1",
            settings_overrides={"selection": {"top_n": 7}},
        )
    )

    assert called["profile_loader"] == "n-halamine"
    assert called["question"] == "hello"
    assert called["offline"] is True
    assert called["selection_top_n"] == 7
    assert response.request_id == "req_1"
    assert response.profile_id == "n-halamine"
    assert response.scoring_summary["selection_top_n"] == 7


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All service tests passed.")
