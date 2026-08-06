from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.repositories.profile_repository import ProfileNotFoundError
from core.repositories.yaml_profile_repository import YamlProfileRepository


def test_yaml_profile_repository_crud_roundtrip() -> None:
    with TemporaryDirectory() as tmp:
        repo = YamlProfileRepository(Path(tmp))

        created = repo.create_profile({"label": "Hydrogel", "default_question": "q1"})
        profile_id = created["id"]
        assert profile_id == "hydrogel"

        listed = repo.list_profiles()
        assert [item.profile_id for item in listed] == ["hydrogel"]

        loaded = repo.get_profile(profile_id)
        assert loaded["label"] == "Hydrogel"

        updated = repo.update_profile(profile_id, {"default_question": "q2"})
        assert updated["profile"]["default_question"] == "q2"

        repo.delete_profile(profile_id)

        try:
            repo.get_profile(profile_id)
        except ProfileNotFoundError:
            pass
        else:
            raise AssertionError("Expected profile to be deleted")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All YAML repository tests passed.")
