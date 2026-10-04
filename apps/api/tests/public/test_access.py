import pytest
from fastapi.testclient import TestClient

from tests.public.conftest import CONSOLE_KEY

pytestmark = pytest.mark.db


def test_public_api_needs_its_own_key(public_client: TestClient) -> None:
    assert public_client.get("/api/public/taxonomy").status_code == 401
    wrong = public_client.get("/api/public/taxonomy", headers={"X-Public-Key": "nope"})
    assert wrong.status_code == 401
    console = public_client.get("/api/public/taxonomy", headers={"X-Public-Key": CONSOLE_KEY})
    assert console.status_code == 401


def test_public_key_does_not_open_the_console(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    response = public_client.get(
        "/api/admin/overview", headers={"X-Console-Key": public_headers["X-Public-Key"]}
    )
    assert response.status_code == 401


def test_public_api_is_closed_without_a_configured_key(unconfigured_client: TestClient) -> None:
    response = unconfigured_client.get("/api/public/taxonomy", headers={"X-Public-Key": ""})
    assert response.status_code == 503


def test_taxonomy_lists_p4_axes(public_client: TestClient, public_headers: dict[str, str]) -> None:
    body = public_client.get("/api/public/taxonomy", headers=public_headers).json()
    assert body["revision"]
    assert len(body["fields"]) == 15
    assert all(len(field["themes"]) == 5 for field in body["fields"])
    assert body["fields"][0]["key"] == "ai_data"
    assert body["fields"][0]["themes"][0]["key"].startswith("ai_data__")
    assert [node["key"] for node in body["businesses"]] == [
        "mx",
        "vd",
        "da",
        "networks",
        "health",
        "harman",
    ]
    assert [node["key"] for node in body["impacts"]] == ["opportunity", "risk", "watch"]
    assert [node["key"] for node in body["scopes"]][:2] == ["dx", "dx_dependency"]
