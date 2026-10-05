from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.collect.models import FetchOutcome, FetchRun
from news_insight.content.ingest import IngestStats, ingest_items
from news_insight.content.models import Item, ItemRevision
from news_insight.sources.enums import StorageRight
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


def raw(n: int, *, title: str | None = None, body: str | None = None) -> RawItem:
    return RawItem(
        stable_id=f"id-{n}",
        url=f"https://www.example.com/{n}?utm_source=rss",
        title=title or f"Title {n}",
        summary="<p>요약 텍스트</p>",
        body=body,
        published_at=NOW,
    )


def persisted(session: Session, **overrides: Any) -> Source:
    source = build_source(**overrides)
    session.add(source)
    session.flush()
    return source


def ingest(session: Session, source: Source, items: list[RawItem], **kwargs: Any) -> IngestStats:
    options: dict[str, Any] = {"fetch_run": None, "now": NOW, "canary": True, **kwargs}
    return ingest_items(session, source, items, **options)


def revision_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(ItemRevision)) or 0


def test_new_items_follow_storage_policy(db_session: Session) -> None:
    source = persisted(db_session, storage_right=StorageRight.METADATA_ONLY)

    stats = ingest(db_session, source, [raw(1)])

    item = db_session.scalars(select(Item)).one()
    assert stats == IngestStats(seen=1, new=1)
    assert item.canonical_url == "https://www.example.com/1"
    assert item.summary is None
    assert (item.revision, item.canary) == (1, True)
    assert [revision.revision for revision in item.revisions] == [1]


def test_unchanged_items_write_nothing(db_session: Session) -> None:
    source = persisted(db_session)
    ingest(db_session, source, [raw(1)])

    stats = ingest(db_session, source, [raw(1)], now=LATER)

    assert stats == IngestStats(seen=1, unchanged=1)
    assert revision_count(db_session) == 1


def test_changed_items_get_a_new_revision(db_session: Session) -> None:
    source = persisted(db_session)
    ingest(db_session, source, [raw(1)])

    stats = ingest(db_session, source, [raw(1, title="Title 1 (updated)")], now=LATER)

    item = db_session.scalars(select(Item)).one()
    assert stats.updated == 1
    assert (item.revision, item.title, item.last_changed_at) == (2, "Title 1 (updated)", LATER)
    assert revision_count(db_session) == 2


def test_batch_duplicates_are_collapsed(db_session: Session) -> None:
    stats = ingest(db_session, persisted(db_session), [raw(1), raw(1)])

    assert (stats.seen, stats.new) == (2, 1)


def test_same_url_under_a_new_id_counts_as_duplicate(db_session: Session) -> None:
    copy = RawItem(stable_id="other-guid", url="https://www.example.com/1", title="Title 1 copy")

    stats = ingest(db_session, persisted(db_session), [raw(1), copy])

    assert (stats.new, stats.duplicate_urls) == (2, 1)


def test_fulltext_ttl_items_expire(db_session: Session) -> None:
    source = persisted(db_session, storage_right=StorageRight.FULLTEXT_TTL)

    ingest(db_session, source, [raw(1, body="<p>Full body</p>")])

    item = db_session.scalars(select(Item)).one()
    assert item.body == "Full body"
    assert item.body_expires_at == NOW + timedelta(days=30)


def test_overlong_ids_are_hashed_and_bad_records_rejected(db_session: Session) -> None:
    long_id = RawItem(stable_id="x" * 600, url="https://www.example.com/long", title="Long id")
    long_url = RawItem(stable_id="bad", url="https://www.example.com/" + "a" * 2100, title="Bad")
    blank = RawItem(stable_id="blank", url="https://www.example.com/blank", title="<p> </p>")

    stats = ingest(db_session, persisted(db_session), [long_id, long_url, blank])

    item = db_session.scalars(select(Item)).one()
    assert (stats.new, stats.rejected) == (1, 2)
    assert item.stable_id.startswith("sha256:")


def test_revisions_link_to_the_fetch_run(db_session: Session) -> None:
    source = persisted(db_session)
    run = FetchRun(source_id=source.id, started_at=NOW, outcome=FetchOutcome.SUCCESS)
    db_session.add(run)
    db_session.flush()

    ingest(db_session, source, [raw(1)], fetch_run=run)

    revision = db_session.scalars(select(ItemRevision)).one()
    assert revision.fetch_run_id == run.id


def test_same_url_and_same_headline_under_a_new_id_is_skipped(db_session: Session) -> None:
    source = persisted(db_session)
    ingest(db_session, source, [raw(1)])
    again = RawItem(stable_id="new-guid", url="https://www.example.com/1", title=raw(1).title)

    stats = ingest(db_session, source, [again])

    assert (stats.new, stats.duplicate_urls) == (0, 1)
    assert db_session.scalar(select(func.count()).select_from(Item)) == 1
