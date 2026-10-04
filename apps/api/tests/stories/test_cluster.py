from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import Track
from news_insight.stories.models import ItemRef, Story, StoryItem
from news_insight.stories.service import SessionScope, cluster
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def scope_for(db_session: Session) -> SessionScope:
    @contextmanager
    def scope() -> Iterator[Session]:
        with db_session.begin_nested():
            yield db_session

    return scope


def add(
    db_session: Session,
    source_key: str,
    track: Track,
    rows: list[tuple[str, str, str, list[str], int]],
    when: datetime = NOW,
) -> None:
    source = db_session.scalars(
        select(__import__("news_insight.sources.models", fromlist=["Source"]).Source).where(
            __import__("news_insight.sources.models", fromlist=["Source"]).Source.key == source_key
        )
    ).one_or_none()
    if source is None:
        source = build_source(key=source_key, name=source_key, track=track)
        db_session.add(source)
        db_session.flush()
    ingest_items(
        db_session,
        source,
        [
            RawItem(stable_id=url, url=url, title=title, summary=summary)
            for url, title, summary, _, _ in rows
        ],
        fetch_run=None,
        now=when,
        canary=True,
    )
    for url, title, _, keywords, relevance in rows:
        item = db_session.scalars(select(Item).where(Item.url == url)).one()
        db_session.add(
            ItemCard(
                item_id=item.id,
                status=CardStatus.READY,
                title_ko=title,
                summary_ko=[],
                keywords=keywords,
                engine="agy",
                model="m",
                input_hash=item.content_hash,
                attempts=0,
                generated_at=when,
                relevance=relevance,
            )
        )
    db_session.flush()


def story_of(db_session: Session, url: str) -> tuple[int, str]:
    row = db_session.execute(
        select(StoryItem.story_id, StoryItem.relation)
        .join(Item, Item.id == StoryItem.item_id)
        .where(Item.url == url)
    ).one()
    return row[0], row[1].value


def test_exact_near_event_and_new_stories(db_session: Session) -> None:
    add(
        db_session,
        "verge",
        Track.NEWS,
        [
            (
                "https://www.verge.com/a/1",
                "삼성전자, 갤럭시 S30 공개…온디바이스 AI 탑재",
                None,
                ["삼성전자", "갤럭시 S30"],
                70,
            ),
        ],
    )
    add(
        db_session,
        "etnews",
        Track.NEWS,
        [
            ("https://m.verge.com/a/1/amp", "다른 제목이지만 같은 URL", None, ["기타"], 10),
            (
                "https://www.etnews.com/2",
                "삼성전자 갤럭시 S30 공개, 온디바이스 AI 탑재했다",
                None,
                ["삼성전자"],
                80,
            ),
            (
                "https://www.etnews.com/3",
                "갤럭시 S30 사전예약 시작, 삼성전자 온디바이스 AI 강조",
                None,
                ["갤럭시 S30"],
                60,
            ),
            (
                "https://www.etnews.com/4",
                "LG디스플레이 2세대 탠덤 OLED 양산 돌입",
                None,
                ["LG디스플레이"],
                50,
            ),
        ],
    )

    stats = cluster(scope_for(db_session), now=NOW)

    seed_story, seed_rel = story_of(db_session, "https://www.verge.com/a/1")
    assert seed_rel == "seed"
    assert story_of(db_session, "https://m.verge.com/a/1/amp") == (seed_story, "exact")
    assert story_of(db_session, "https://www.etnews.com/2") == (seed_story, "near")
    event_story, event_rel = story_of(db_session, "https://www.etnews.com/3")
    assert (event_story, event_rel) == (seed_story, "event")
    other_story, other_rel = story_of(db_session, "https://www.etnews.com/4")
    assert other_story != seed_story and other_rel == "seed"
    assert stats.processed == 5
    story = db_session.get(Story, seed_story)
    assert story is not None
    assert (story.item_count, story.source_count, story.max_relevance) == (4, 2, 80)
    assert story.title_ko == "삼성전자 갤럭시 S30 공개, 온디바이스 AI 탑재했다"
    assert cluster(scope_for(db_session), now=NOW).processed == 0


def test_old_stories_are_not_extended_and_refs_are_recorded(db_session: Session) -> None:
    old = NOW - timedelta(days=5)
    add(
        db_session,
        "verge",
        Track.NEWS,
        [("https://www.verge.com/old", "애플 아이폰 18 공개 행사 개최", None, ["애플"], 50)],
        when=old,
    )
    cluster(scope_for(db_session), now=old)
    add(
        db_session,
        "arxiv",
        Track.RESEARCH_IP,
        [
            (
                "https://arxiv.org/abs/2610.01985v1",
                "애플 아이폰 18 공개 행사 개최",
                "code github.com/apple/ml-x",
                ["애플"],
                50,
            ),
        ],
    )

    cluster(scope_for(db_session), now=NOW)

    assert story_of(db_session, "https://arxiv.org/abs/2610.01985v1")[1] == "seed"
    refs = set(db_session.execute(select(ItemRef.kind, ItemRef.value)).tuples())
    assert refs == {("arxiv", "2610.01985"), ("github", "apple/ml-x")}
