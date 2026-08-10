"""Unit tests for `core.config.Settings`."""

from __future__ import annotations

import yaml

from core.config import ALL_SOURCES, Settings


def test_defaults_run_without_any_config_file() -> None:
    settings = Settings()

    assert settings.profile == "generic"
    assert settings.search.enabled_sources == ALL_SOURCES
    assert settings.selection.enabled is True
    assert settings.profile_repository.mode == "local"


def test_from_dict_overrides_only_the_supplied_subset() -> None:
    settings = Settings.from_dict({"profile": "n-halamine", "selection": {"top_n": 5}})

    assert settings.profile == "n-halamine"
    assert settings.selection.top_n == 5
    assert settings.selection.min_relevance == 30.0  # untouched default


def test_from_dict_ignores_unknown_nested_keys() -> None:
    """Unknown keys are dropped rather than raising, so an old config still boots."""
    settings = Settings.from_dict({"search": {"timeout_seconds": 11, "not_a_real_knob": 1}})

    assert settings.search.timeout_seconds == 11
    assert not hasattr(settings.search, "not_a_real_knob")


def test_from_dict_tolerates_none_and_empty_payloads() -> None:
    assert Settings.from_dict({}).profile == "generic"
    assert Settings.from_dict({"search": None, "selection": None}).search.timeout_seconds == 20


def test_api_key_is_trimmed_and_missing_keys_are_empty_strings() -> None:
    settings = Settings.from_dict({"api_keys": {"semantic_scholar": "  abc  ", "openalex": None}})

    assert settings.api_key("semantic_scholar") == "abc"
    assert settings.api_key("openalex") == ""
    assert settings.api_key("absent") == ""


def test_load_reads_yaml_from_disk(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"profile": "custom", "search": {"concurrent_workers": 2}}), encoding="utf-8")

    settings = Settings.load(path)

    assert settings.profile == "custom"
    assert settings.search.concurrent_workers == 2


def test_load_of_a_missing_path_returns_defaults(tmp_path) -> None:
    assert Settings.load(tmp_path / "nope.yaml") == Settings()
    assert Settings.load(None) == Settings()


def test_load_of_an_empty_file_returns_defaults(tmp_path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")

    assert Settings.load(path) == Settings()


def test_source_http_overrides_survive_the_round_trip(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump({"search": {"source_http_overrides": {"crossref": {"max_attempts": 2}}}}),
        encoding="utf-8",
    )

    settings = Settings.load(path)

    assert settings.search.source_http_overrides == {"crossref": {"max_attempts": 2}}
