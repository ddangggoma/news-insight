import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.cards.service import MAX_ATTEMPTS, pending_items
from news_insight.collect.contracts import RawItem
from news_insight.content.hide import BACKUP_COLUMNS, HIDDEN, find_junk, hide, write_backup
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import StorageRight
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 11, 4, 3, tzinfo=UTC)
BASE = "https://www.clien.net/service/board"


def seeded(db_session: Session) -> Source:
    source = build_source(
        key="clien-test",
        storage_right=StorageRight.EXCERPT_ALLOWED,
        config={"exclude_pattern": "/service/board/(rule|annonce)/"},
    )
    db_session.add(source)
    db_session.flush()
    urls = {
        "post": f"{BASE}/news/19000001",
        "rule": f"{BASE}/rule/10707403",
        "notice": f"{BASE}/annonce/18708788",
        "old-rule": f"{BASE}/rule/10707404",
    }
    ingest_items(
        db_session,
        source,
        [RawItem(stable_id=t, url=u, title=t, summary="요약") for t, u in urls.items()],
        fetch_run=None,
        now=NOW,
        canary=True,
    )
    old = db_session.scalars(select(Item).where(Item.title == "old-rule")).one()
    old.published_at = old.first_seen_at - timedelta(days=3000)  # archive: out of the reader
    db_session.add(
        ItemCard(
            item_id=db_session.scalars(select(Item.id).where(Item.title == "rule")).one(),
            status=CardStatus.READY,
            input_hash="x",
            title_ko="규칙",
            scope="dx",
            generated_at=NOW,
        )
    )
    db_session.flush()
    return source


def test_finds_only_visible_items_the_rules_refuse(db_session: Session) -> None:
    source = seeded(db_session)

    visible, total = find_junk(db_session, source)

    assert sorted(found.item.title for found in visible) == ["notice", "rule"]
    assert total == 3  # the archive page counts as refused but is already out of the reader


def test_hide_keeps_every_row_and_removes_the_item_from_the_queue_and_reader(
    db_session: Session, tmp_path: Path
) -> None:
    source = seeded(db_session)
    visible, _ = find_junk(db_session, source)
    backup = tmp_path / "hidden.csv"
    write_backup(backup, source, visible)

    hide(db_session, visible, reason="board rule page", now=NOW)

    cards = {
        title: card
        for title, card in db_session.execute(
            select(Item.title, ItemCard).join(ItemCard, ItemCard.item_id == Item.id)
        ).tuples()
    }
    assert db_session.scalars(select(Item)).all().__len__() == 4  # nothing deleted
    for title in ("rule", "notice"):
        assert cards[title].status is CardStatus.FAILED
        assert cards[title].attempts == MAX_ATTEMPTS
        assert cards[title].error == f"{HIDDEN}board rule page"
    assert cards["rule"].title_ko == "규칙"  # the old card text stays for an undo
    assert "post" not in cards
    # the carder neither retries a hidden item nor picks up one that never had a card
    assert [item.title for item, _ in pending_items(db_session, limit=10)] == ["post"]
    # a second run has nothing left to do
    assert find_junk(db_session, source)[0] == []

    rows = list(csv.DictReader(backup.open(encoding="utf-8")))
    assert tuple(rows[0]) == BACKUP_COLUMNS
    by_title = {row["title"]: row for row in rows}
    assert by_title["rule"]["had_card"] == "True" and by_title["rule"]["old_status"] == "ready"
    assert by_title["rule"]["old_scope"] == "dx"
    assert by_title["notice"]["had_card"] == "False"


def test_keep_regex_rescues_and_hide_regex_adds(db_session: Session) -> None:
    import re

    source = seeded(db_session)

    kept, _ = find_junk(db_session, source, keep=re.compile("/rule/"))
    added, _ = find_junk(db_session, source, hide=re.compile("/news/"))

    assert [found.item.title for found in kept] == ["notice"]
    assert sorted(found.item.title for found in added) == ["notice", "post", "rule"]
