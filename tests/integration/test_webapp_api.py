"""HTTP contract of the FastAPI adapter, driven through the real ASGI app.

`TestClient` speaks to the app in-process (no socket), so routing, dependency
wiring, validation and the error-shape handlers are all real.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.factories import profile_payload

VALID_PROFILE = profile_payload(name="hydrogel", label="Hydrogel")


# --- read endpoints ----------------------------------------------------------


def test_settings_endpoint_never_leaks_repository_headers(api_client: TestClient) -> None:
    payload = api_client.get("/api/settings").json()

    assert payload["search"]["enabled_sources"] == []
    assert "headers" not in payload["profile_repository"]
    assert "profile" not in payload  # the default profile is served by /api/profiles


def test_profile_list_reports_ids_metadata_and_the_default(api_client: TestClient) -> None:
    payload = api_client.get("/api/profiles").json()

    assert payload["profiles"] == ["generic"]
    assert payload["default"] == "generic"
    assert payload["profiles_meta"][0]["id"] == "generic"
    assert payload["profiles_meta"][0]["is_builtin"] is True


def test_a_single_profile_is_returned_under_an_id_envelope(api_client: TestClient) -> None:
    payload = api_client.get("/api/profiles/generic").json()

    assert payload["id"] == "generic"
    assert payload["profile"]["label"] == "Generic"


def test_an_unknown_profile_is_a_404_in_the_error_shape(api_client: TestClient) -> None:
    response = api_client.get("/api/profiles/nope")

    assert response.status_code == 404
    assert response.json() == {"error": "Unknown profile 'nope'"}


@pytest.mark.parametrize("bad_id", ["Upper", "with%20space", "..", "x" * 200])
def test_malformed_profile_ids_are_rejected_before_the_storage_layer(api_client: TestClient, bad_id) -> None:
    response = api_client.get(f"/api/profiles/{bad_id}")

    assert response.status_code in {400, 404}
    assert "error" in response.json()


# --- write endpoints ---------------------------------------------------------


def test_creating_a_profile_returns_201_and_the_stored_payload(api_client: TestClient) -> None:
    response = api_client.post("/api/profiles", json=VALID_PROFILE)

    assert response.status_code == 201
    assert response.json()["id"] == "hydrogel"
    assert api_client.get("/api/profiles").json()["profiles"] == ["generic", "hydrogel"]


def test_creating_a_duplicate_profile_is_a_409(api_client: TestClient) -> None:
    api_client.post("/api/profiles", json=VALID_PROFILE)

    response = api_client.post("/api/profiles", json=VALID_PROFILE)

    assert response.status_code == 409
    assert "already exists" in response.json()["error"]


def test_an_invalid_profile_payload_is_a_400(api_client: TestClient) -> None:
    response = api_client.post("/api/profiles", json={"default_question": "no label"})

    assert response.status_code == 400
    assert "label is required" in response.json()["error"]


def test_updating_and_deleting_need_no_account_in_local_mode(api_client: TestClient) -> None:
    api_client.post("/api/profiles", json=VALID_PROFILE)

    updated = api_client.put("/api/profiles/hydrogel", json={"label": "Hydrogel", "default_question": "q2"})
    deleted = api_client.delete("/api/profiles/hydrogel")

    assert updated.status_code == 200
    assert updated.json()["profile"]["default_question"] == "q2"
    assert deleted.json() == {"deleted": "hydrogel"}
    assert api_client.get("/api/profiles/hydrogel").status_code == 404


def test_deleting_a_built_in_profile_is_a_403(api_client: TestClient) -> None:
    response = api_client.delete("/api/profiles/generic")

    assert response.status_code == 403
    assert "protected" in response.json()["error"]


# --- validation and error shape ---------------------------------------------


def test_a_run_request_without_a_profile_id_is_a_400(api_client: TestClient) -> None:
    response = api_client.post("/api/run", json={"question": "q"})

    assert response.status_code == 400
    assert "profile_id" in response.json()["error"]


def test_unknown_run_request_fields_are_rejected(api_client: TestClient) -> None:
    response = api_client.post("/api/run", json={"question": "q", "profile_id": "generic", "sneaky": 1})

    assert response.status_code == 400
    assert "sneaky" in response.json()["error"]


def test_an_over_long_question_is_rejected(api_client: TestClient) -> None:
    response = api_client.post("/api/run", json={"question": "x" * 1001, "profile_id": "generic"})

    assert response.status_code == 400


def test_an_oversized_body_is_rejected_by_the_middleware(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/profiles",
        content=json.dumps(VALID_PROFILE).encode(),
        headers={"Content-Type": "application/json", "Content-Length": str(2 * 1024 * 1024)},
    )

    assert response.status_code == 413
    assert response.json() == {"error": "Request body too large."}


def test_a_contract_violation_from_core_becomes_a_400(api_client: TestClient) -> None:
    """A profile with no default question + an empty box has nothing to search."""
    api_client.put("/api/profiles/generic", json={"label": "Generic", "default_question": ""})

    response = api_client.post("/api/run", json={"question": "  ", "profile_id": "generic"})

    assert response.status_code == 400
    assert response.json() == {"error": "question is required"}


def test_every_failure_uses_the_error_key_not_detail(api_client: TestClient) -> None:
    """The UI reads `{"error": ...}`; FastAPI's default `{"detail": ...}` would break it."""
    for response in (
        api_client.get("/api/profiles/nope"),
        api_client.post("/api/run", json={}),
        api_client.get("/api/definitely-not-a-route"),
        api_client.delete("/api/profiles/generic"),
    ):
        assert response.status_code >= 400
        assert set(response.json()) == {"error"}


# --- static UI ---------------------------------------------------------------


def test_the_index_page_is_served_at_the_root(api_client: TestClient) -> None:
    response = api_client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
