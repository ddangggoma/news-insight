"""Backfill for cards made before classification existed, or under an older taxonomy.

- `relink_keywords`: canonical keyword links from stored card keywords (no LLM call).
- `run_classify`: labels for ready cards not classified at the current taxonomy revision,
  from their Korean title and summary only, with the same Antigravity → Qwen switching.
Both are idempotent: what is already done at the current revision is skipped.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from news_insight.cards.engines import EngineOutput, LabelEngine, MeteredLabelEngine
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.cards.schemas import LabelInput, parse_labels
from news_insight.cards.service import (
    CardPolicy,
    CardRunStats,
    Clock,
    Lane,
    SessionScope,
    drive_engines,
    store_labels,
)
from news_insight.classify.keywords import AliasSeed, get_alias_seed
from news_insight.classify.models import ItemKeyword
from news_insight.classify.store import link_keywords
from news_insight.classify.taxonomy import Taxonomy, get_taxonomy
from news_insight.content.models import Item

RELINK_BATCH = 500


def _now() -> datetime:
    return datetime.now(UTC)


def unclassified_condition(revision: int) -> Any:
    return (
        ItemCard.status == CardStatus.READY,
        or_(ItemCard.taxonomy_rev.is_(None), ItemCard.taxonomy_rev != revision),
    )


def unclassified_count(session: Session, revision: int) -> int:
    statement = select(func.count()).select_from(ItemCard).where(*unclassified_condition(revision))
    return session.scalar(statement) or 0


def unlinked_condition() -> Any:
    return (
        ItemCard.status == CardStatus.READY,
        func.jsonb_array_length(ItemCard.keywords) > 0,
        ~exists().where(ItemKeyword.item_id == ItemCard.item_id),
    )


def unlinked_count(session: Session) -> int:
    statement = select(func.count()).select_from(ItemCard).where(*unlinked_condition())
    return session.scalar(statement) or 0


def relink_keywords(
    open_session: SessionScope,
    *,
    seed: AliasSeed | None = None,
    limit: int | None,
    relink_all: bool,
    clock: Clock = _now,
) -> int:
    """Link stored card keywords to canonical keywords; returns the number of cards done.

    By default only cards without links; `relink_all` recomputes every ready card (after
    editing the alias seed).
    """
    seed = seed or get_alias_seed()
    conditions = (ItemCard.status == CardStatus.READY,) if relink_all else unlinked_condition()
    done, last_id = 0, 0
    while limit is None or done < limit:
        size = RELINK_BATCH if limit is None else min(RELINK_BATCH, limit - done)
        with open_session() as session:
            rows = session.execute(
                select(ItemCard.item_id, ItemCard.keywords, Item.first_seen_at)
                .join(Item, Item.id == ItemCard.item_id)
                .where(*conditions, ItemCard.item_id > last_id)
                .order_by(ItemCard.item_id)
                .limit(size)
            ).tuples()
            batch = list(rows)
            now = clock()
            for item_id, keywords, first_seen_at in batch:
                link_keywords(
                    session, item_id, list(keywords), seen_at=first_seen_at, now=now, seed=seed
                )
        if not batch:
            break
        done += len(batch)
        last_id = batch[-1][0]
    return done


def run_classify(
    open_session: SessionScope,
    *,
    agy: MeteredLabelEngine | None,
    qwen: LabelEngine | None,
    policy: CardPolicy,
    limit: int | None,
    taxonomy: Taxonomy | None = None,
    clock: Clock = _now,
    monotonic: Callable[[], float] = time.monotonic,
) -> CardRunStats:
    """Classify ready cards that lack labels at the current taxonomy revision.

    Items an engine leaves out are counted as failed and not retried within the run.
    """
    taxonomy = taxonomy or get_taxonomy()
    stats = CardRunStats()
    attempted: set[int] = set()

    def load(size: int) -> list[LabelInput]:
        if limit is not None:
            size = min(size, limit - len(attempted))
        if size <= 0:
            return []
        with open_session() as session:
            statement = (
                select(ItemCard.item_id, ItemCard.title_ko, ItemCard.summary_ko, Item.title)
                .join(Item, Item.id == ItemCard.item_id)
                .where(*unclassified_condition(taxonomy.revision))
                .order_by(Item.first_seen_at.desc(), Item.id.desc())
                .limit(size)
            )
            if attempted:
                statement = statement.where(ItemCard.item_id.notin_(attempted))
            rows = list(session.execute(statement).tuples())
        attempted.update(item_id for item_id, *_ in rows)
        return [
            LabelInput(id=item_id, title=title_ko or title, summary=list(summary))
            for item_id, title_ko, summary, title in rows
        ]

    def store(engine: str, inputs: list[LabelInput], output: EngineOutput) -> None:
        found = parse_labels(output.raw, inputs, taxonomy)
        now: datetime = clock()
        with open_session() as session:
            for entry in inputs:
                labels = found.get(entry.id)
                card = session.scalars(
                    select(ItemCard).where(ItemCard.item_id == entry.id)
                ).one_or_none()
                if labels is None or card is None:
                    stats.failed += 1
                    continue
                store_labels(
                    session,
                    card,
                    labels,
                    taxonomy=taxonomy,
                    engine=engine,
                    model=output.model,
                    now=now,
                )
                stats.ready += 1

    drive_engines(
        Lane(agy.name, policy.agy_batch, agy.classify, agy.usage) if agy else None,
        Lane(qwen.name, policy.qwen_batch, qwen.classify) if qwen else None,
        policy=policy,
        stats=stats,
        load=load,
        store=store,
        monotonic=monotonic,
    )
    return stats
