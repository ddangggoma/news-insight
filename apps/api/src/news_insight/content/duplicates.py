"""Duplicate assignment before carding: each item either is a root or repeats an earlier root.

Keys come from content/dedup.py. An item repeats the earliest matching root, by key in the
order url > text > link > title; a root that already has a card wins over one that has not.
Carding skips repeats and copies the root's card to them (cards/service.py).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from news_insight.content.dedup import DedupKeys, titles_agree
from news_insight.content.models import ItemDedup

PRIORITY = ("url", "text", "link", "title")
SOCIAL_METHODS = frozenset({"activitypub", "atproto"})


@dataclass(frozen=True)
class Candidate:
    item_id: int
    root: int
    url: str
    text: str | None
    title: str | None
    lead: str | None
    lead_title: bool
    carded: bool = False


def pick_root(
    item_id: int, keys: DedupKeys, candidates: Iterable[Candidate]
) -> tuple[int, str] | None:
    """The root an item repeats and the key that matched, or None for a new story."""
    best: tuple[int, int, int, str] | None = None  # (priority, not carded, root, kind)
    for c in candidates:
        if c.item_id >= item_id or c.root >= item_id:
            continue  # only earlier items: deterministic and free of cycles
        kind = None
        if c.url == keys.url:
            kind = "url"
        elif keys.text is not None and c.text == keys.text:
            kind = "text"
        elif keys.link is not None and c.url == keys.link:
            kind = "link"
        elif (
            keys.title is not None
            and c.title == keys.title
            and titles_agree(keys.lead, keys.lead_title, c.lead, c.lead_title)
        ):
            kind = "title"
        if kind is None:
            continue
        rank = (PRIORITY.index(kind), 0 if c.carded else 1, c.root, kind)
        if best is None or rank < best:
            best = rank
    return (best[2], best[3]) if best else None


def candidates_for(session: Session, keys: DedupKeys) -> list[Candidate]:
    from news_insight.cards.models import CardStatus, ItemCard

    conditions = [ItemDedup.url_key == keys.url]
    if keys.text:
        conditions.append(ItemDedup.text_key == keys.text)
    if keys.link:
        conditions.append(ItemDedup.url_key == keys.link)
    if keys.title:
        conditions.append(ItemDedup.title_key == keys.title)
    rows = session.execute(
        select(ItemDedup, ItemCard.status)
        .outerjoin(ItemCard, ItemCard.item_id == ItemDedup.item_id)
        .where(or_(*conditions))
        .limit(200)
    ).tuples()
    return [
        Candidate(
            item_id=d.item_id,
            root=d.duplicate_of or d.item_id,
            url=d.url_key,
            text=d.text_key,
            title=d.title_key,
            lead=d.lead_key,
            lead_title=d.lead_title,
            carded=status == CardStatus.READY,
        )
        for d, status in rows
    ]


def record(
    session: Session, item_id: int, keys: DedupKeys, *, now: datetime, changed: bool
) -> ItemDedup:
    """Store an item's keys and assign its root. `changed`: the content changed, so items that
    repeated this one no longer do (they get their own card)."""
    if changed:
        session.execute(
            update(ItemDedup)
            .where(ItemDedup.duplicate_of == item_id)
            .values(duplicate_of=None, matched_by=None)
        )
    match = pick_root(item_id, keys, candidates_for(session, keys))
    row = session.get(ItemDedup, item_id)
    if row is None:
        row = ItemDedup(item_id=item_id)
        session.add(row)
    row.url_key, row.text_key, row.title_key = keys.url, keys.text, keys.title
    row.lead_key, row.lead_title, row.link_key = keys.lead, keys.lead_title, keys.link
    row.duplicate_of, row.matched_by = match if match else (None, None)
    row.computed_at = now
    session.flush()
    return row


@dataclass
class BackfillStats:
    keyed: int = 0
    repeats: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    links: int = 0


def backfill(session: Session, *, now: datetime, chunk: int = 5000) -> BackfillStats:
    """Keys and roots for items stored before item_dedup existed (or by another ingest path).

    Social posts stored before links were kept get theirs back from the text: Mastodon's split
    link spans are glued in every possible way, and a reconstruction counts only when it is
    the URL of an item we have."""
    from news_insight.cards.models import CardStatus, ItemCard
    from news_insight.content.dedup import dedup_keys, text_links, url_key
    from news_insight.content.models import Item
    from news_insight.sources.models import Source

    known_urls = set(session.scalars(select(ItemDedup.url_key)))
    missing = (
        session.execute(
            select(
                Item.id,
                Item.canonical_url,
                Item.title,
                Item.summary,
                Item.body,
                Source.access_method,
                ItemCard.status,
            )
            .join(Source, Source.id == Item.source_id)
            .outerjoin(ItemCard, ItemCard.item_id == Item.id)
            .outerjoin(ItemDedup, ItemDedup.item_id == Item.id)
            .where(ItemDedup.item_id.is_(None))
            .order_by(Item.id)
        )
        .tuples()
        .all()
    )
    keys: dict[int, DedupKeys] = {}
    carded: dict[int, bool] = {}
    for item_id, canonical, title, summary, body, _method, status in missing:
        keys[item_id] = dedup_keys(
            canonical=canonical, title=title, summary=summary, body=body, link=None
        )
        carded[item_id] = status == CardStatus.READY
        known_urls.add(keys[item_id].url)
    stats = BackfillStats()
    social = {item_id for item_id, *_, method, _ in missing if str(method) in SOCIAL_METHODS}
    for item_id, _canonical, _, summary, body, *_ in missing:
        if item_id not in social:
            continue
        own = keys[item_id].url
        for candidate in text_links(summary or body):
            key = url_key(candidate)
            if key != own and key in known_urls:
                keys[item_id] = replace(keys[item_id], link=key)
                stats.links += 1
                break

    # in-memory indexes over existing rows and the new ones, filled in id order
    index: dict[str, dict[str, list[Candidate]]] = {k: {} for k in ("url", "text", "title")}

    def add(c: Candidate) -> None:
        index["url"].setdefault(c.url, []).append(c)
        if c.text:
            index["text"].setdefault(c.text, []).append(c)
        if c.title:
            index["title"].setdefault(c.title, []).append(c)

    existing = session.execute(
        select(ItemDedup, ItemCard.status).outerjoin(
            ItemCard, ItemCard.item_id == ItemDedup.item_id
        )
    ).tuples()
    for d, status in existing:
        add(
            Candidate(
                d.item_id,
                d.duplicate_of or d.item_id,
                d.url_key,
                d.text_key,
                d.title_key,
                d.lead_key,
                d.lead_title,
                status == CardStatus.READY,
            )
        )
    pending: list[ItemDedup] = []
    for item_id in sorted(keys):
        k = keys[item_id]
        pool = [*index["url"].get(k.url, [])]
        if k.text:
            pool += index["text"].get(k.text, [])
        if k.link:
            pool += index["url"].get(k.link, [])
        if k.title:
            pool += index["title"].get(k.title, [])
        match = pick_root(item_id, k, pool)
        root, kind = match if match else (None, None)
        pending.append(
            ItemDedup(
                item_id=item_id,
                url_key=k.url,
                text_key=k.text,
                title_key=k.title,
                lead_key=k.lead,
                lead_title=k.lead_title,
                link_key=k.link,
                duplicate_of=root,
                matched_by=kind,
                computed_at=now,
            )
        )
        if kind:
            stats.repeats += 1
            stats.by_kind[kind] = stats.by_kind.get(kind, 0) + 1
        add(
            Candidate(
                item_id,
                root or item_id,
                k.url,
                k.text,
                k.title,
                k.lead,
                k.lead_title,
                carded[item_id],
            )
        )
        stats.keyed += 1
        if len(pending) >= chunk:
            session.add_all(pending)
            session.flush()
            pending.clear()
    session.add_all(pending)
    session.flush()
    return stats
