import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.taxonomy.seed import backfill_labels, seed_taxonomy
from tests.public.seed import Spec, seed_corpus

pytestmark = pytest.mark.db

PATENTS = (
    Spec(
        "Foldable OLED hinge patent", "verge", 3, "display_av", ("display_av__display_panel",), "ip"
    ),
    Spec(
        "OLED compensation patent filed",
        "etnews",
        30,
        "display_av",
        ("display_av__display_panel",),
        "ip",
    ),
    Spec("NPU patent dispute", "verge", 24 * 40, "ai", ("ai__ai_agents",), "ip"),
    Spec("Irrelevant patent troll story", "verge", 4, None, (), "ip", scope="irrelevant"),
)


def test_patent_view_counts_ip_cards_by_period_and_area(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    seed_corpus(db_session, PATENTS)
    seed_taxonomy(db_session)
    backfill_labels(db_session)
    body = public_client.get("/api/public/patents", headers=public_headers).json()
    assert body["kind"] == "month" and len(body["periods"]) == 12
    assert body["periods"][-1]["key"] == "2026-10"
    assert sum(p["total"] for p in body["periods"]) == 3  # the irrelevant one is left out
    assert body["periods"][-1]["office"] == 0
    titles = [i["title"] for i in body["recent"]["items"]]
    assert "Foldable OLED hinge patent" in titles and "Irrelevant patent troll story" not in titles
    areas = {n["label"]: n for n in body["nodes"]}
    assert areas, "technology areas from the card labels"
    top = body["nodes"][0]
    assert len(top["counts"]) == 12 and top["current"] == top["counts"][-1]

    quarters = public_client.get(
        "/api/public/patents", params={"kind": "quarter"}, headers=public_headers
    ).json()
    assert len(quarters["periods"]) == 8 and quarters["periods"][-1]["key"] == "2026-Q4"
    assert sum(p["total"] for p in quarters["periods"]) == 3
