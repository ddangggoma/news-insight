"""Seen ledger: store new items, record real changes as revisions, skip unchanged ones."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.collect.models import FetchRun
from news_insight.content import duplicates
from news_insight.content.dedup import DedupKeys, dedup_keys, shared_link
from news_insight.content.models import Item, ItemMetricSnapshot, ItemRevision
from news_insight.content.normalize import canonical_url, clean_text, content_hash, stable_key
from news_insight.content.policy import apply_storage_right
from news_insight.sources.models import Source

MAX_URL = 2048
TITLE_LIMIT = 1000
AUTHOR_LIMIT = 300
METRIC_SNAPSHOT_INTERVAL = timedelta(hours=1)


@dataclass(frozen=True)
class IngestStats:
    seen: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicate_urls: int = 0
    rejected: int = 0
    snapshots: int = 0


@dataclass(frozen=True)
class _Prepared:
    stable_id: str
    url: str
    canonical: str
    title: str
    summary: str | None
    body: str | None
    author: str | None
    published_at: datetime | None
    digest: str
    metrics: dict[str, int]
    link: str | None  # the article a social post shares


def _prepare(raw: RawItem, *, social: bool = False) -> _Prepared | None:
    title = clean_text(raw.title, limit=TITLE_LIMIT)
    url = raw.url.strip()
    canonical = canonical_url(url) if url else ""
    if not title or not canonical or len(url) > MAX_URL or len(canonical) > MAX_URL:
        return None
    summary = clean_text(raw.summary)
    body = clean_text(raw.body)
    link = raw.link or (shared_link(raw.summary or raw.body, post_url=url) if social else None)
    return _Prepared(
        stable_id=stable_key(raw.stable_id or canonical),
        url=url,
        canonical=canonical,
        title=title,
        summary=summary,
        body=body,
        author=clean_text(raw.author, limit=AUTHOR_LIMIT),
        published_at=raw.published_at,
        digest=content_hash(title, summary, body),
        metrics=dict(raw.metrics),
        link=link,
    )


def keys_of(item: Item, link: str | None) -> DedupKeys:
    """Keys from the stored text (summary first: the body may expire), so a backfill and a
    later ingest of the same text agree."""
    return dedup_keys(
        canonical=item.canonical_url,
        title=item.title,
        summary=item.summary,
        body=item.body,
        link=link,
    )


def _apply(item: Item, candidate: _Prepared, source: Source, now: datetime) -> None:
    stored = apply_storage_right(
        source.storage_right, summary=candidate.summary, body=candidate.body, now=now
    )
    item.url = candidate.url
    item.canonical_url = candidate.canonical
    item.title = candidate.title
    item.summary = stored.summary
    item.body = stored.body
    item.body_expires_at = stored.body_expires_at
    item.author = candidate.author
    item.published_at = candidate.published_at
    item.content_hash = candidate.digest


def ingest_items(
    session: Session,
    source: Source,
    items: Sequence[RawItem],
    *,
    fetch_run: FetchRun | None,
    now: datetime,
    canary: bool,
) -> IngestStats:
    prepared: dict[str, _Prepared] = {}
    rejected = 0
    social = str(source.access_method) in duplicates.SOCIAL_METHODS
    for raw in items:
        candidate = _prepare(raw, social=social)
        if candidate is None:
            rejected += 1
            continue
        prepared.setdefault(candidate.stable_id, candidate)
    if not prepared:
        return IngestStats(seen=len(items), rejected=rejected)

    existing = {
        item.stable_id: item
        for item in session.scalars(
            select(Item).where(Item.source_id == source.id, Item.stable_id.in_(list(prepared)))
        )
    }
    url_owners: dict[str, str] = {}
    owner_titles: dict[str, str] = {}
    for url, stable_id, title in session.execute(
        select(Item.canonical_url, Item.stable_id, Item.title).where(
            Item.source_id == source.id,
            Item.canonical_url.in_({candidate.canonical for candidate in prepared.values()}),
        )
    ).tuples():
        url_owners.setdefault(url, stable_id)
        owner_titles.setdefault(url, title)
    run_id = fetch_run.id if fetch_run is not None else None
    new = updated = unchanged = duplicate_urls = 0
    touched: dict[str, Item] = {}
    keyed: list[tuple[Item, DedupKeys, bool]] = []  # new or changed items: (item, keys, changed)
    for candidate in prepared.values():
        item = existing.get(candidate.stable_id)
        if item is None:
            owner = url_owners.setdefault(candidate.canonical, candidate.stable_id)
            owner_titles.setdefault(candidate.canonical, candidate.title)
            if owner != candidate.stable_id:
                duplicate_urls += 1
                # same link and same headline under a new GUID: the same report again, not a new
                # one (2026-10-05: 355 such copies). Podcast episodes that share one link keep
                # their own titles and are stored.
                if (
                    owner_titles[candidate.canonical].strip().lower()
                    == candidate.title.strip().lower()
                ):
                    continue
            item = Item(
                source_id=source.id,
                track=source.track,
                stable_id=candidate.stable_id,
                revision=1,
                canary=canary,
                first_seen_at=now,
                last_changed_at=now,
            )
            _apply(item, candidate, source, now)
            session.add(item)
            touched[candidate.stable_id] = item
            keyed.append((item, keys_of(item, candidate.link), False))
            new += 1
        elif item.content_hash == candidate.digest:
            touched[candidate.stable_id] = item
            unchanged += 1  # seen-ledger hit: no write, nothing to reprocess downstream
            continue
        else:
            item.revision += 1
            item.canary = canary
            item.last_changed_at = now
            _apply(item, candidate, source, now)
            touched[candidate.stable_id] = item
            keyed.append((item, keys_of(item, candidate.link), True))
            updated += 1
        session.add(
            ItemRevision(
                item=item,
                revision=item.revision,
                content_hash=candidate.digest,
                title=candidate.title,
                fetch_run_id=run_id,
                recorded_at=now,
            )
        )
    session.flush()
    # duplicate assignment comes before carding: repeats never reach a card engine
    for item, keys, changed in sorted(keyed, key=lambda entry: entry[0].id):
        duplicates.record(session, item.id, keys, now=now, changed=changed)
    snapshots = _record_snapshots(session, touched, prepared, now)
    return IngestStats(
        seen=len(items),
        new=new,
        updated=updated,
        unchanged=unchanged,
        duplicate_urls=duplicate_urls,
        rejected=rejected,
        snapshots=snapshots,
    )


def _record_snapshots(
    session: Session, touched: dict[str, Item], prepared: dict[str, _Prepared], now: datetime
) -> int:
    """Record changed metrics at most once per METRIC_SNAPSHOT_INTERVAL per item."""
    observed = {
        touched[stable_id].id: candidate.metrics
        for stable_id, candidate in prepared.items()
        if candidate.metrics and stable_id in touched
    }
    if not observed:
        return 0
    latest = {
        snapshot.item_id: snapshot
        for snapshot in session.scalars(
            select(ItemMetricSnapshot)
            .where(ItemMetricSnapshot.item_id.in_(list(observed)))
            .order_by(ItemMetricSnapshot.item_id, ItemMetricSnapshot.captured_at.desc())
            .distinct(ItemMetricSnapshot.item_id)
        )
    }
    recorded = 0
    for item_id, metrics in observed.items():
        last = latest.get(item_id)
        if last is not None and (
            last.metrics == metrics or now - last.captured_at < METRIC_SNAPSHOT_INTERVAL
        ):
            continue
        session.add(ItemMetricSnapshot(item_id=item_id, captured_at=now, metrics=metrics))
        recorded += 1
    session.flush()
    return recorded
