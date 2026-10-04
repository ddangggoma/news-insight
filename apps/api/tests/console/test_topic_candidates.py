from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.console.topics import candidate_key
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from tests.factories import build_source

pytestmark = pytest.mark.db


def seed(db_session: Session, candidates: list[list[str]], *, scope: str = "dx") -> None:
    source = build_source()
    db_session.add(source)
    db_session.flush()
    now = datetime.now(UTC)
    for index in range(len(candidates)):
        url = f"https://www.example.com/{scope}/{index}"
        ingest_items(
            db_session,
            source,
            [RawItem(stable_id=url, url=url, title=f"t{index}")],
            fetch_run=None,
            now=now - timedelta(days=index),
            canary=True,
        )

    for index, item in enumerate(db_session.scalars(select(Item).order_by(Item.id))):
        db_session.add(
            ItemCard(
                item_id=item.id,
                status=CardStatus.READY,
                title_ko=f"카드 {index}",
                summary_ko=[],
                keywords=[],
                input_hash=item.content_hash,
                generated_at=now,
                field="connectivity",
                scope=scope,
                relevance=50 + index,
                topic_candidates=candidates[index],
            )
        )
    db_session.flush()


def test_candidates_group_spelling_variants(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    seed(db_session, [["위성 직접통신"], ["위성직접통신", "액체냉각"], ["위성-직접통신"], []])

    body = console_client.get("/api/admin/topic-candidates", headers=headers).json()

    assert [c["key"] for c in body] == [candidate_key("위성 직접통신")]
    top = body[0]
    assert top["count"] == 3 and top["fields"] == {"connectivity": 3}
    assert len(top["examples"]) == 3 and top["examples"][0]["title_ko"] == "카드 2"
    single = console_client.get(
        "/api/admin/topic-candidates", params={"min_count": 1}, headers=headers
    ).json()
    assert len(single) == 2 and single[1]["label"] == "액체냉각"
