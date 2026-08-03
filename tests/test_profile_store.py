from __future__ import annotations

import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.profile_store import (
    ProtectedProfileError,
    create_profile,
    delete_profile,
    list_profiles,
    update_profile,
)


def _write_profile(path: Path, name: str, label: str) -> None:
    payload = {
        "name": name,
        "label": label,
        "default_question": "",
        "concepts": [],
        "query_groups": {},
        "off_topic_terms": [],
        "journal_terms": [],
        "term_groups": {},
        "intents": {},
        "buckets": [],
        "extraction_fields": [],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_list_profiles_orders_generic_then_created_desc(tmp_path: Path):
    _write_profile(tmp_path / "generic.yaml", "generic", "General literature search")
    _write_profile(tmp_path / "older.yaml", "older", "Older profile")
    time.sleep(1.1)
    _write_profile(tmp_path / "newer.yaml", "newer", "Newer profile")

    listed = list_profiles(tmp_path)
    assert [item.profile_id for item in listed] == ["generic", "newer", "older"]


def test_create_profile_generates_unique_safe_id(tmp_path: Path):
    first = create_profile({"label": "My Profile!!!", "default_question": "q1"}, tmp_path)
    second = create_profile({"label": "My Profile!!!", "default_question": "q2"}, tmp_path)

    assert first["id"] == "my-profile"
    assert second["id"] == "my-profile-2"
    assert (tmp_path / "my-profile.yaml").exists()
    assert (tmp_path / "my-profile-2.yaml").exists()


def test_update_profile_partial_keeps_existing_fields(tmp_path: Path):
    created = create_profile(
        {
            "label": "Hydrogel search",
            "default_question": "old",
            "off_topic_terms": ["silver"],
        },
        tmp_path,
    )

    update_profile(created["id"], {"default_question": "new"}, tmp_path)
    updated_yaml = yaml.safe_load((tmp_path / f"{created['id']}.yaml").read_text(encoding="utf-8"))

    assert updated_yaml["label"] == "Hydrogel search"
    assert updated_yaml["default_question"] == "new"
    assert updated_yaml["off_topic_terms"] == ["silver"]


def test_delete_profile_rejects_protected_generic(tmp_path: Path):
    _write_profile(tmp_path / "generic.yaml", "generic", "General literature search")

    try:
        delete_profile("generic", tmp_path)
    except ProtectedProfileError:
        pass
    else:
        raise AssertionError("Expected generic profile deletion to be blocked")
