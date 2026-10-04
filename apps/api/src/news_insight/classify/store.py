"""Persistence for item labels and canonical keyword links."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from news_insight.classify.keywords import AliasSeed, clean_keyword, keyword_key
from news_insight.classify.models import (
    AliasOrigin,
    ItemKeyword,
    ItemLabel,
    Keyword,
    KeywordAlias,
    LabelMethod,
)
from news_insight.classify.taxonomy import Axis, Labels


def empty_labels() -> Labels:
    return {axis: [] for axis in Axis}


def current_labels(session: Session, item_ids: Sequence[int]) -> dict[int, Labels]:
    """Current (not superseded) labels per item, every axis present, in assignment order."""
    if not item_ids:
        return {}
    rows = session.execute(
        select(ItemLabel.item_id, ItemLabel.axis, ItemLabel.node_key)
        .where(ItemLabel.item_id.in_(item_ids), ItemLabel.superseded_at.is_(None))
        .order_by(ItemLabel.item_id, ItemLabel.id)
    ).tuples()
    found: dict[int, Labels] = {}
    for item_id, axis, key in rows:
        found.setdefault(item_id, empty_labels())[axis].append(key)
    return found


def apply_labels(
    session: Session,
    item_id: int,
    labels: Labels | None,
    *,
    taxonomy_rev: int,
    method: LabelMethod,
    engine: str | None,
    model: str | None,
    now: datetime,
) -> None:
    """Make `labels` the item's current labels; None clears them.

    Rows are never deleted: changed labels supersede the current rows (append-only).
    """
    current = list(
        session.scalars(
            select(ItemLabel)
            .where(ItemLabel.item_id == item_id, ItemLabel.superseded_at.is_(None))
            .order_by(ItemLabel.id)
        )
    )
    wanted = [(axis, key) for axis, keys in (labels or {}).items() for key in keys]
    unchanged = {(row.axis, row.node_key) for row in current} == set(wanted) and all(
        row.taxonomy_rev == taxonomy_rev for row in current
    )
    if unchanged:
        return
    if current:
        session.execute(
            update(ItemLabel)
            .where(ItemLabel.id.in_([row.id for row in current]))
            .values(superseded_at=now)
        )
    session.add_all(
        ItemLabel(
            item_id=item_id,
            axis=axis,
            node_key=key,
            confidence=None,
            method=method,
            taxonomy_rev=taxonomy_rev,
            engine=engine,
            model=model,
            labeled_at=now,
        )
        for axis, key in wanted
    )
    session.flush()


def _keyword_named(session: Session, canonical: str, seen_at: datetime, now: datetime) -> int:
    """Id of the canonical keyword (by its own matching key or exact name), created if new."""
    key = keyword_key(canonical) or canonical
    found = session.scalar(select(KeywordAlias.keyword_id).where(KeywordAlias.alias == key))
    if found is None:
        session.execute(
            insert(Keyword)
            .values(canonical=canonical, first_seen_at=seen_at, created_at=now)
            .on_conflict_do_nothing(index_elements=[Keyword.canonical])
        )
        found = session.scalars(select(Keyword.id).where(Keyword.canonical == canonical)).one()
        _add_alias(session, key, found, AliasOrigin.AUTO, now)
    return found


def _add_alias(
    session: Session,
    key: str,
    keyword_id: int,
    origin: AliasOrigin,
    now: datetime,
    *,
    repoint: bool = False,
) -> None:
    statement = insert(KeywordAlias).values(
        alias=key, keyword_id=keyword_id, origin=origin, created_at=now
    )
    if repoint:
        statement = statement.on_conflict_do_update(
            index_elements=[KeywordAlias.alias],
            set_={"keyword_id": keyword_id, "origin": origin},
            where=KeywordAlias.keyword_id != keyword_id,
        )
    else:
        statement = statement.on_conflict_do_nothing(index_elements=[KeywordAlias.alias])
    session.execute(statement)


def resolve_keyword(
    session: Session, text: str, *, seen_at: datetime, now: datetime, seed: AliasSeed
) -> int | None:
    """Canonical keyword id for a free-text keyword; creates the keyword on first sight.

    The curated seed wins over aliases learned automatically (it re-points them).
    """
    key = keyword_key(text)
    display = clean_keyword(text)
    if key is None or display is None:
        return None
    canonical = seed.by_key.get(key)
    if canonical is not None:
        keyword_id = _keyword_named(session, canonical, seen_at, now)
        _add_alias(session, key, keyword_id, AliasOrigin.SEED, now, repoint=True)
    else:
        found = session.scalar(select(KeywordAlias.keyword_id).where(KeywordAlias.alias == key))
        keyword_id = found if found is not None else _keyword_named(session, display, seen_at, now)
    session.execute(
        update(Keyword)
        .where(Keyword.id == keyword_id, Keyword.first_seen_at > seen_at)
        .values(first_seen_at=seen_at)
    )
    return keyword_id


def link_keywords(
    session: Session,
    item_id: int,
    keywords: Sequence[str],
    *,
    seen_at: datetime,
    now: datetime,
    seed: AliasSeed,
) -> list[int]:
    """Make the item's canonical keyword links match its card keywords (idempotent).

    `seen_at` is when the item was first seen: it dates the keyword's first sighting.
    """
    wanted: list[int] = []
    for text in keywords:
        keyword_id = resolve_keyword(session, text, seen_at=seen_at, now=now, seed=seed)
        if keyword_id is not None and keyword_id not in wanted:
            wanted.append(keyword_id)
    existing = set(
        session.scalars(select(ItemKeyword.keyword_id).where(ItemKeyword.item_id == item_id))
    )
    stale = existing - set(wanted)
    if stale:
        session.execute(
            delete(ItemKeyword).where(
                ItemKeyword.item_id == item_id, ItemKeyword.keyword_id.in_(stale)
            )
        )
    session.add_all(
        ItemKeyword(item_id=item_id, keyword_id=keyword_id, linked_at=now)
        for keyword_id in wanted
        if keyword_id not in existing
    )
    session.flush()
    return wanted
