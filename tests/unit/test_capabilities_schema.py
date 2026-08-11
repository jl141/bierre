"""The WS-0 capability schema is itself an artefact, so it is tested like one.

`GET /api/capabilities` is built in WS-D and asserted against this schema there.
What this file proves is narrower: the schema is valid, its two documented modes
validate, and the mode invariants that keep local mode account-free actually bite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "webapp" / "schemas" / "capabilities.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture
def local(schema: dict) -> dict:
    return dict(schema["examples"][0])


@pytest.fixture
def hosted(schema: dict) -> dict:
    return dict(schema["examples"][1])


def test_both_documented_modes_validate(validator: Draft202012Validator, local: dict, hosted: dict) -> None:
    assert local["mode"] == "local"
    assert hosted["mode"] == "hosted"
    validator.validate(local)
    validator.validate(hosted)


def test_default_locale_is_one_of_the_shipped_locales(local: dict, hosted: dict) -> None:
    """Not expressible in JSON Schema, so it is asserted here and in WS-D."""
    for capabilities in (local, hosted):
        assert capabilities["default_locale"] in capabilities["locales"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_write", False),
        ("auth", True),
        ("accounts_base", "/accounts"),
        ("history", "server"),
        ("max_subscriptions", 5),
        ("auth_methods", ["password"]),
    ],
)
def test_local_mode_cannot_claim_an_account_feature(
    validator: Draft202012Validator, local: dict, field: str, value: object
) -> None:
    assert not validator.is_valid({**local, field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("auth", False),
        ("accounts", False),
        ("accounts_base", None),
        ("history", "local"),
        ("history_retention", None),
    ],
)
def test_hosted_mode_cannot_drop_identity_or_server_history(
    validator: Draft202012Validator, hosted: dict, field: str, value: object
) -> None:
    assert not validator.is_valid({**hosted, field: value})


def test_an_unknown_capability_is_rejected(validator: Draft202012Validator, local: dict) -> None:
    """A typo in a flag name must fail loudly, not be silently ignored by the UI."""
    assert not validator.is_valid({**local, "dark_mode": True})


def test_a_missing_capability_is_rejected(validator: Draft202012Validator, local: dict) -> None:
    del local["legal_urls"]

    assert not validator.is_valid(local)
