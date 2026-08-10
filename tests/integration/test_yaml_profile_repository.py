"""`YamlProfileRepository` against a real temporary directory.

These use the filesystem on purpose — atomic writes, id generation from
filenames and directory listing order are the behaviour under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.repositories.profile_repository import (
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileValidationError,
    ProtectedProfileError,
)
from core.repositories.yaml_profile_repository import YamlProfileRepository, generate_profile_id
from tests.factories import profile_payload


def test_crud_round_trip(yaml_repo: YamlProfileRepository, profiles_dir: Path) -> None:
    created = yaml_repo.create_profile(profile_payload())
    profile_id = created["id"]

    assert profile_id == "hydrogel-search"
    assert (profiles_dir / "hydrogel-search.yaml").exists()
    assert [item.profile_id for item in yaml_repo.list_profiles()] == ["hydrogel-search"]
    assert yaml_repo.get_profile(profile_id)["label"] == "Hydrogel Search"

    updated = yaml_repo.update_profile(profile_id, {"label": "Hydrogel Search", "default_question": "q2"})
    assert updated["profile"]["default_question"] == "q2"

    yaml_repo.delete_profile(profile_id)
    with pytest.raises(ProfileNotFoundError):
        yaml_repo.get_profile(profile_id)


def test_an_explicit_name_wins_over_the_label_slug(yaml_repo: YamlProfileRepository) -> None:
    created = yaml_repo.create_profile(profile_payload(name="custom-id", label="Totally Different"))

    assert created["id"] == "custom-id"


def test_creating_the_same_label_twice_produces_a_suffixed_id(yaml_repo: YamlProfileRepository) -> None:
    first = yaml_repo.create_profile(profile_payload(label="Hydrogel"))
    second = yaml_repo.create_profile(profile_payload(label="Hydrogel"))

    assert (first["id"], second["id"]) == ("hydrogel", "hydrogel-2")


def test_creating_an_existing_explicit_id_is_a_conflict(yaml_repo: YamlProfileRepository) -> None:
    yaml_repo.create_profile(profile_payload(name="taken", label="Taken"))

    with pytest.raises(ProfileConflictError, match="already exists"):
        yaml_repo.create_profile(profile_payload(name="taken", label="Taken"))


@pytest.mark.parametrize("bad_id", ["../escape", "Upper", "with space", "trailing-", "", "a--b"])
def test_unsafe_profile_ids_are_rejected(yaml_repo: YamlProfileRepository, bad_id: str) -> None:
    """Ids become filenames, so the grammar is the path-traversal defence."""
    with pytest.raises(ProfileValidationError):
        yaml_repo.get_profile(bad_id)


def test_a_missing_label_is_rejected(yaml_repo: YamlProfileRepository) -> None:
    with pytest.raises(ProfileValidationError, match="label is required"):
        yaml_repo.create_profile({"default_question": "q"})


def test_unknown_fields_are_rejected_rather_than_silently_stored(yaml_repo: YamlProfileRepository) -> None:
    with pytest.raises(ProfileValidationError, match="Unknown profile fields: colour"):
        yaml_repo.create_profile(profile_payload(colour="blue"))


def test_a_malformed_bucket_is_reported_as_a_validation_error(yaml_repo: YamlProfileRepository) -> None:
    with pytest.raises(ProfileValidationError, match="Invalid profile payload"):
        yaml_repo.create_profile(profile_payload(buckets=[{"id": "core", "nope": True}]))


def test_update_merges_with_the_stored_payload(yaml_repo: YamlProfileRepository) -> None:
    yaml_repo.create_profile(profile_payload(name="p", label="P", off_topic_terms=["silver"]))

    updated = yaml_repo.update_profile("p", {"default_question": "new question"})

    assert updated["profile"]["off_topic_terms"] == ["silver"]  # preserved
    assert updated["profile"]["default_question"] == "new question"


def test_updating_a_missing_profile_is_a_not_found(yaml_repo: YamlProfileRepository) -> None:
    with pytest.raises(ProfileNotFoundError):
        yaml_repo.update_profile("ghost", {"label": "Ghost"})


def test_built_in_profiles_cannot_be_deleted(yaml_repo: YamlProfileRepository) -> None:
    yaml_repo.create_profile(profile_payload(name="generic", label="Generic"))

    with pytest.raises(ProtectedProfileError, match="protected"):
        yaml_repo.delete_profile("generic")


def test_deleting_a_missing_profile_is_a_not_found(yaml_repo: YamlProfileRepository) -> None:
    with pytest.raises(ProfileNotFoundError):
        yaml_repo.delete_profile("ghost")


def test_listing_puts_generic_first_then_newest_created(yaml_repo: YamlProfileRepository) -> None:
    yaml_repo.create_profile(profile_payload(name="older", label="Older"))
    yaml_repo.create_profile(profile_payload(name="newer", label="Newer"))
    yaml_repo.create_profile(profile_payload(name="generic", label="Generic"))

    listed = [item.profile_id for item in yaml_repo.list_profiles()]

    assert listed[0] == "generic"
    assert set(listed[1:]) == {"older", "newer"}


def test_listing_marks_built_in_profiles(yaml_repo: YamlProfileRepository) -> None:
    yaml_repo.create_profile(profile_payload(name="generic", label="Generic"))
    yaml_repo.create_profile(profile_payload(name="custom", label="Custom"))

    flags = {item.profile_id: item.is_builtin for item in yaml_repo.list_profiles()}

    assert flags == {"generic": True, "custom": False}


def test_listing_survives_an_unreadable_yaml_file(yaml_repo: YamlProfileRepository, profiles_dir: Path) -> None:
    """One corrupt file must not take the whole profile dropdown down."""
    (profiles_dir / "broken.yaml").write_text("::: not yaml :::", encoding="utf-8")

    listed = {item.profile_id: item.label for item in yaml_repo.list_profiles()}

    assert listed["broken"] == "broken"


def test_listing_a_missing_directory_returns_nothing(tmp_path: Path) -> None:
    assert YamlProfileRepository(tmp_path / "absent").list_profiles() == []


def test_stored_yaml_holds_the_full_normalised_schema(yaml_repo: YamlProfileRepository, profiles_dir: Path) -> None:
    yaml_repo.create_profile(profile_payload(name="p", label="P"))

    stored = yaml.safe_load((profiles_dir / "p.yaml").read_text(encoding="utf-8"))

    assert set(stored) == {
        "name",
        "label",
        "default_question",
        "concepts",
        "query_groups",
        "off_topic_terms",
        "journal_terms",
        "term_groups",
        "intents",
        "buckets",
        "extraction_fields",
    }


def test_writes_leave_no_temporary_files_behind(yaml_repo: YamlProfileRepository, profiles_dir: Path) -> None:
    yaml_repo.create_profile(profile_payload(name="p", label="P"))

    assert [path.name for path in profiles_dir.iterdir()] == ["p.yaml"]


def test_generated_ids_are_slugified_and_length_bounded(profiles_dir: Path) -> None:
    assert generate_profile_id("Café — Ünïcode Läbel!", profiles_dir) == "cafe-unicode-label"
    assert generate_profile_id("", profiles_dir) == "profile"
    assert len(generate_profile_id("x" * 200, profiles_dir)) <= 64
