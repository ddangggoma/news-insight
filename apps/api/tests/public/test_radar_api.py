from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.public.seed import seed_corpus

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def corpus(db_session: Session) -> dict[str, int]:
    return seed_corpus(db_session)


def get(client: TestClient, headers: dict[str, str], path: str, **params: Any) -> Any:
    response = client.get(f"/api/public/{path}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_radar_defaults_to_the_current_iso_week(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "radar", period="week")
    window = body["window"]
    assert (window["kind"], window["key"]) == ("week", "2026-W40")
    assert (window["prev_key"], window["next_key"]) == ("2026-W39", "2026-W41")
    assert window["is_current"] is True


def test_radar_heatmap_crosses_fields_and_businesses(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "radar", period="week", key="2026-W40")
    cells = {(c["field"], c["business"]): (c["count"], c["previous"]) for c in body["cells"]}
    assert cells == {
        ("ai_data", "mx"): (2, 0),
        ("display_media", "vd"): (2, 0),
        ("display_media", "mx"): (1, 0),
        ("network_comms", "networks"): (0, 1),
    }
    kpis = body["kpis"]
    assert (kpis["total"], kpis["previous_total"]) == (4, 1)
    assert kpis["new_stories"] == 1
    assert kpis["cross_track_stories"] == 0
    assert kpis["hottest"] == {"field": "ai_data", "business": "mx", "count": 2, "previous": 0}


def test_radar_momentum_hype_and_keyword_shifts(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "radar", period="week", key="2026-W40")
    momentum = {row["key"]: row for row in body["momentum"]}
    assert momentum["ai_data"]["counts"] == [0, 0, 0, 0, 0, 0, 0, 2]
    assert momentum["ai_data"]["change"] is None
    assert momentum["network_comms"]["counts"][-2:] == [1, 0]
    assert momentum["network_comms"]["change"] == -100.0
    assert [row["key"] for row in body["momentum"]][:2] == ["ai_data", "display_media"]
    hype = {row["key"]: row for row in body["hype"]}
    assert (hype["ai_data"]["chatter"], hype["ai_data"]["research"]) == (2, 0)
    assert (hype["display_media"]["chatter"], hype["display_media"]["research"]) == (0, 2)
    shifts = {row["key"]: row for row in body["keywords"]}
    assert shifts["oled"]["state"] == "new"
    assert shifts["ai에이전트"]["state"] == "rising"
    assert shifts["ai에이전트"]["counts"] == [0, 0, 0, 1, 2]


def test_radar_cell_detail(public_client: TestClient, public_headers: dict[str, str]) -> None:
    body = get(
        public_client,
        public_headers,
        "radar/cell",
        period="week",
        key="2026-W40",
        field="display_media",
        business="vd",
    )
    assert (body["count"], body["previous"]) == (2, 0)
    assert body["trend"] == [0, 0, 0, 0, 0, 0, 0, 2]
    assert body["themes"] == [{"key": "display_media__oled_microled", "count": 2}]
    assert body["keywords"][0] == {"key": "oled", "label": "OLED", "count": 2}
    assert {row["title"] for row in body["stories"]} == {
        "OLED burn-in compensation",
        "oled-compensation repo",
    }


def test_radar_cell_without_business(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(
        public_client,
        public_headers,
        "radar/cell",
        period="week",
        key="2026-W40",
        field="semiconductor",
        business="none",
        scope="all",
    )
    assert body["count"] == 1
    assert [row["title"] for row in body["stories"]] == ["HBM capacity expansion"]


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("radar", {"period": "year"}),
        ("radar", {"period": "week", "key": "2026-W99"}),
        ("radar", {"period": "week", "scope": "nope"}),
        ("radar/cell", {"period": "week", "field": "nope", "business": "mx"}),
        ("radar/cell", {"period": "week", "field": "ai_data", "business": "nope"}),
    ],
)
def test_radar_rejects_invalid_parameters(
    public_client: TestClient, public_headers: dict[str, str], path: str, params: dict[str, Any]
) -> None:
    response = public_client.get(f"/api/public/{path}", params=params, headers=public_headers)
    assert response.status_code == 422
