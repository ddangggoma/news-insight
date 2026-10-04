from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.cards.service import classify_pending_count
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.public.filters import ReaderFilters
from news_insight.taxonomy.catalog import PROVISIONAL_REVISION
from news_insight.taxonomy.provisional import apply_provisional
from tests.factories import build_source

pytestmark = pytest.mark.db


def old_card(db_session: Session, title: str, themes: list[str], keywords: list[str]) -> ItemCard:
    source = db_session.scalars(select(build_source().__class__)).first()
    if source is None:
        source = build_source()
        db_session.add(source)
        db_session.flush()
    url = f"https://www.example.com/{title}"
    ingest_items(
        db_session,
        source,
        [RawItem(stable_id=url, url=url, title=title)],
        fetch_run=None,
        now=datetime.now(UTC),
        canary=True,
    )
    item = db_session.scalars(select(Item).where(Item.url == url)).one()
    card = ItemCard(
        item_id=item.id,
        status=CardStatus.READY,
        title_ko=title,
        summary_ko=[],
        keywords=keywords,
        input_hash=item.content_hash,
        generated_at=datetime.now(UTC),
        field=themes[0].split("__")[0] if themes else None,
        themes=themes,
        businesses=["mx"],
        scope="dx",
        taxonomy_revision="2026-10-04.1",
    )
    db_session.add(card)
    db_session.flush()
    return card


def test_old_cards_move_to_v2_and_stay_queued_for_the_llm(db_session: Session) -> None:
    direct = old_card(db_session, "6g", ["network_comms__fiveg_sixg"], ["6G"])
    market = old_card(db_session, "price", ["product_market__pricing_revenue"], ["Matter", "가격"])
    bare = old_card(db_session, "bare", ["product_market__pricing_revenue"], ["가격"])

    result = apply_provisional(db_session)
    for card in (direct, market, bare):
        db_session.refresh(card)

    assert (result.mapped, result.from_keywords, result.without_theme) == (1, 1, 1)
    assert direct.themes == ["connectivity__cellular_5g_6g"] and direct.field == "connectivity"
    assert market.themes == ["connectivity__smart_home_iot"] and market.signal_type == "market"
    assert bare.themes == [] and bare.businesses == []
    assert {c.taxonomy_revision for c in (direct, market, bare)} == {PROVISIONAL_REVISION}
    visible = db_session.scalar(
        select(ItemCard.id)
        .join(Item, Item.id == ItemCard.item_id)
        .where(*ReaderFilters.build(scope="all", q=None).conditions(), ItemCard.id == direct.id)
    )
    assert visible == direct.id
    assert classify_pending_count(db_session) >= 3
    assert apply_provisional(db_session).mapped == 0  # idempotent
