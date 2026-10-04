from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.classify.keywords import AliasSeed, keyword_key
from news_insight.classify.models import ItemKeyword, ItemLabel, Keyword, KeywordAlias, LabelMethod
from news_insight.classify.store import apply_labels, current_labels, link_keywords
from news_insight.classify.taxonomy import Axis
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 4, 3, tzinfo=UTC)
SEED = AliasSeed(
    by_key={
        keyword_key(v) or "": canonical
        for canonical, variants in {
            "온디바이스 AI": ["온디바이스 AI", "On-device AI"],
            "삼성전자": ["삼성전자", "Samsung Electronics"],
        }.items()
        for v in variants
    }
)


def seed_items(db_session: Session, titles: list[str]) -> dict[str, Item]:
    source = build_source()
    db_session.add(source)
    db_session.flush()
    ingest_items(
        db_session,
        source,
        [RawItem(stable_id=t, url=f"https://www.example.com/{t}", title=t) for t in titles],
        fetch_run=None,
        now=NOW,
        canary=True,
    )
    return {item.title: item for item in db_session.scalars(select(Item))}


def link(
    db_session: Session,
    item_id: int,
    keywords: list[str],
    *,
    seen_at: datetime = NOW,
    seed: AliasSeed = SEED,
) -> list[int]:
    return link_keywords(db_session, item_id, keywords, seen_at=seen_at, now=NOW, seed=seed)


def canonicals(db_session: Session, item: Item) -> list[str]:
    rows = db_session.scalars(
        select(Keyword.canonical)
        .join(ItemKeyword, ItemKeyword.keyword_id == Keyword.id)
        .where(ItemKeyword.item_id == item.id)
        .order_by(Keyword.canonical)
    )
    return list(rows)


def test_keyword_variants_link_to_one_canonical_keyword(db_session: Session) -> None:
    items = seed_items(db_session, ["a", "b"])

    link(db_session, items["a"].id, ["온디바이스AI", "Samsung Electronics", "AI칩"])
    link(db_session, items["b"].id, ["#온디바이스 ai", "삼성전자", "AI 칩", "  "])

    assert canonicals(db_session, items["a"]) == ["AI칩", "삼성전자", "온디바이스 AI"]
    assert canonicals(db_session, items["b"]) == canonicals(db_session, items["a"])
    assert db_session.scalar(select(Keyword).where(Keyword.canonical == "AI칩")) is not None
    assert len(list(db_session.scalars(select(Keyword)))) == 3


def test_relinking_replaces_the_set_and_keeps_the_earliest_first_seen(db_session: Session) -> None:
    items = seed_items(db_session, ["a"])
    item_id = items["a"].id
    link(db_session, item_id, ["갤럭시", "폴더블"])
    link(db_session, item_id, ["갤럭시", "XR"], seen_at=NOW - timedelta(days=2))
    link(db_session, item_id, ["갤럭시", "XR"], seen_at=NOW - timedelta(days=2))

    assert canonicals(db_session, items["a"]) == ["XR", "갤럭시"]
    galaxy = db_session.scalars(select(Keyword).where(Keyword.canonical == "갤럭시")).one()
    assert galaxy.first_seen_at == NOW - timedelta(days=2)


def test_seed_alias_takes_over_an_auto_alias(db_session: Session) -> None:
    items = seed_items(db_session, ["a", "b"])
    link(db_session, items["a"].id, ["Apple"], seed=AliasSeed(by_key={}))
    seed = AliasSeed(by_key={"apple": "애플", "애플": "애플"})

    link(db_session, items["b"].id, ["apple"], seed=seed)

    assert canonicals(db_session, items["b"]) == ["애플"]
    alias = db_session.scalars(select(KeywordAlias).where(KeywordAlias.alias == "apple")).one()
    assert alias.keyword.canonical == "애플"


def test_labels_are_replaced_append_only(db_session: Session) -> None:
    items = seed_items(db_session, ["a"])
    item_id = items["a"].id
    first = {Axis.FIELD: ["ai", "display"], Axis.PRODUCT: [], Axis.IMPACT: ["opportunity"]}
    common = {"method": LabelMethod.LLM, "engine": "agy", "model": "gemini", "now": NOW}

    apply_labels(db_session, item_id, first, taxonomy_rev=1, **common)
    apply_labels(db_session, item_id, first, taxonomy_rev=1, **common)  # unchanged: no-op
    assert current_labels(db_session, [item_id]) == {item_id: first}
    assert len(list(db_session.scalars(select(ItemLabel)))) == 3

    second = {Axis.FIELD: ["ai"], Axis.PRODUCT: ["phone"], Axis.IMPACT: ["risk"]}
    apply_labels(db_session, item_id, second, taxonomy_rev=2, **common)

    assert current_labels(db_session, [item_id]) == {item_id: second}
    rows = list(db_session.scalars(select(ItemLabel)))
    assert len(rows) == 6
    assert sum(row.superseded_at is not None for row in rows) == 3
    assert {row.taxonomy_rev for row in rows if row.superseded_at is None} == {2}

    apply_labels(db_session, item_id, None, taxonomy_rev=2, **common)

    assert current_labels(db_session, [item_id]) == {}
