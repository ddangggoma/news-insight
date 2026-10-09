import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.public.board import _claim_area
from news_insight.taxonomy.seed import backfill_labels, seed_taxonomy
from tests.public.seed import Spec, seed_corpus

pytestmark = pytest.mark.db

OLED = ("display_av__display_panel",)
EXTRA = (
    Spec("OLED price war", "verge", 3, "display_av", OLED, "market", "risk", relevance=90),
    Spec("OLED new fab", "verge", 4, "display_av", OLED, "supply", "opportunity", relevance=40),
)


def test_board_counts_impacts_by_area_with_evidence(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    seed_corpus(db_session, EXTRA)
    seed_taxonomy(db_session)
    backfill_labels(db_session)
    body = public_client.get("/api/public/board", headers=public_headers).json()
    assert len(body["personas"]) == 31 and body["persona"] is None
    rows = {r["key"]: r for r in body["rows"]}
    panel = rows["display_av__display_panel"]
    assert panel["counts"]["risk"] >= 1 and panel["counts"]["opportunity"] >= 2
    assert panel["evidence"]["risk"][0]["title"] == "[KO] OLED price war"
    assert set(panel["horizons"]) == {"1y", "3y", "5y"}
    # a persona with no briefing readings keeps the whole board
    chosen = public_client.get(
        "/api/public/board", params={"persona": "vd_head"}, headers=public_headers
    ).json()
    assert chosen["persona"] == "vd_head" and chosen["rows"]


def test_a_claim_lands_on_the_area_most_of_its_cards_belong_to() -> None:
    assert _claim_area([1, 2, 3], {1: 10, 2: 20, 3: 20}) == 20
    assert _claim_area([9], {1: 10}) is None
