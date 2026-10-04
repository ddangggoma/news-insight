"""Korean card generation: pending selection, engine switching, storage and run records."""

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from news_insight.cards.engines import (
    CardEngine,
    EngineError,
    EngineOutput,
    MeteredEngine,
    Quota,
)
from news_insight.cards.models import CardRun, CardStatus, ItemCard
from news_insight.cards.schemas import CardDraft, CardInput, parse_drafts
from news_insight.classify.keywords import AliasSeed, get_alias_seed
from news_insight.classify.models import LabelMethod
from news_insight.classify.store import apply_labels, link_keywords
from news_insight.classify.taxonomy import Labels, Taxonomy, get_taxonomy
from news_insight.content.models import Item
from news_insight.content.normalize import truncate
from news_insight.sources.models import Source

MAX_ATTEMPTS = 3
EXCERPT_LIMIT = 500
SessionScope = Callable[[], AbstractContextManager[Session]]
Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(UTC)


def pending_condition() -> Any:
    """No card yet, the item changed since its card, or a failed card with retries left."""
    return or_(
        ItemCard.id.is_(None),
        ItemCard.input_hash != Item.content_hash,
        and_(ItemCard.status == CardStatus.FAILED, ItemCard.attempts < MAX_ATTEMPTS),
    )


def pending_items(session: Session, *, limit: int) -> list[tuple[Item, Source]]:
    statement = (
        select(Item, Source)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .where(pending_condition())
        .order_by(Item.first_seen_at.desc(), Item.id.desc())
        .limit(limit)
    )
    return list(session.execute(statement).tuples())


def pending_count(session: Session) -> int:
    statement = (
        select(func.count())
        .select_from(Item)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .where(pending_condition())
    )
    return session.scalar(statement) or 0


def card_input(item: Item, source: Source) -> CardInput:
    excerpt = item.summary or item.body
    return CardInput(
        id=item.id,
        title=item.title,
        source=source.name,
        language=source.language,
        excerpt=truncate(excerpt, EXCERPT_LIMIT) if excerpt else None,
    )


def store_labels(
    session: Session,
    card: ItemCard,
    labels: Labels | None,
    *,
    taxonomy: Taxonomy,
    engine: str,
    model: str,
    now: datetime,
) -> None:
    """Record the card's taxonomy labels; None (engine sent none) leaves it for the backfill."""
    apply_labels(
        session,
        card.item_id,
        labels,
        taxonomy_rev=taxonomy.revision,
        method=LabelMethod.LLM,
        engine=engine,
        model=model,
        now=now,
    )
    card.taxonomy_rev = taxonomy.revision if labels is not None else None


def store_result(
    session: Session,
    item: Item,
    draft: CardDraft | None,
    *,
    engine: str,
    model: str,
    error: str | None,
    now: datetime,
    taxonomy: Taxonomy | None = None,
    seed: AliasSeed | None = None,
) -> ItemCard:
    card = session.scalars(select(ItemCard).where(ItemCard.item_id == item.id)).one_or_none()
    if card is None:
        card = ItemCard(item_id=item.id, attempts=0, summary_ko=[], keywords=[])
        session.add(card)
    changed = card.input_hash != item.content_hash
    card.input_hash = item.content_hash
    card.generated_at = now
    card.engine, card.model = engine, model
    if draft is not None:
        card.status = CardStatus.READY
        card.title_ko, card.summary_ko, card.keywords = (
            draft.title_ko,
            draft.summary_ko,
            draft.keywords,
        )
        card.attempts, card.error = 0, None
        session.flush()
        store_labels(
            session,
            card,
            draft.labels,
            taxonomy=taxonomy or get_taxonomy(),
            engine=engine,
            model=model,
            now=now,
        )
        link_keywords(
            session,
            item.id,
            draft.keywords,
            seen_at=item.first_seen_at,
            now=now,
            seed=seed or get_alias_seed(),
        )
    else:
        card.status = CardStatus.FAILED
        card.attempts = 1 if changed else card.attempts + 1
        card.error = error
    session.flush()
    return card


@dataclass
class CardRunStats:
    ready: int = 0
    failed: int = 0
    batches: dict[str, int] = field(default_factory=dict)
    quota: dict[str, int | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CardPolicy:
    agy_batch: int = 100
    qwen_batch: int = 5
    min_weekly: int = 10  # D18: cards may use 90 % of the weekly Antigravity limit
    min_five_hour: int = 2
    time_budget_seconds: float = 540.0


@dataclass(frozen=True)
class Lane[T]:
    """One engine as the run driver sees it: its batch size, the call and its quota probe."""

    name: str
    batch: int
    call: Callable[[list[T]], EngineOutput]
    usage: Callable[[], Quota] | None = None


def drive_engines[T](
    primary: Lane[T] | None,
    fallback: Lane[T] | None,
    *,
    policy: CardPolicy,
    stats: CardRunStats,
    load: Callable[[int], list[T]],
    store: Callable[[str, list[T], EngineOutput], None],
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """Run batches until `load` has nothing left or the time budget is spent.

    The primary (Antigravity) is used while its quota allows (D18); when it is spent,
    unavailable or failing, the run continues on the fallback (local Qwen, user request
    2026-10-04). A fallback failure stops the run and leaves the rest for the next one.
    """
    deadline = monotonic() + policy.time_budget_seconds
    use_primary = primary is not None
    switch = f"switching to {fallback.name}" if fallback else "no fallback engine"

    def refresh_quota() -> None:
        nonlocal use_primary
        if primary is None or primary.usage is None or not use_primary:
            return
        try:
            quota = primary.usage()
        except EngineError as exc:
            stats.notes.append(f"{primary.name} usage unavailable: {exc}")
            use_primary = False
            return
        stats.quota = quota.as_dict()
        if not quota.usable(min_weekly=policy.min_weekly, min_five_hour=policy.min_five_hour):
            stats.notes.append(f"{primary.name} quota reserved ({quota.as_dict()}): {switch}")
            use_primary = False

    refresh_quota()
    while monotonic() < deadline:
        lane = primary if use_primary else fallback
        if lane is None:
            stats.notes.append("no engine available")
            break
        inputs = load(lane.batch)
        if not inputs:
            break
        try:
            output = lane.call(inputs)
        except EngineError as exc:
            if lane is primary:
                stats.notes.append(f"{exc}: {switch}")
                use_primary = False
                continue
            stats.notes.append(str(exc))
            break  # local model down: leave items pending for the next run
        store(lane.name, inputs, output)
        stats.batches[lane.name] = stats.batches.get(lane.name, 0) + 1
        if lane is primary:
            refresh_quota()


def run_cards(
    open_session: SessionScope,
    *,
    agy: MeteredEngine | None,
    qwen: CardEngine | None,
    policy: CardPolicy,
    clock: Clock = _now,
    monotonic: Callable[[], float] = time.monotonic,
    taxonomy: Taxonomy | None = None,
    seed: AliasSeed | None = None,
) -> CardRunStats:
    """Generate cards (with taxonomy labels and canonical keywords) for pending items."""
    stats = CardRunStats()
    taxonomy = taxonomy or get_taxonomy()
    seed = seed or get_alias_seed()

    def load(size: int) -> list[CardInput]:
        with open_session() as session:
            return [card_input(item, source) for item, source in pending_items(session, limit=size)]

    def store(engine: str, inputs: list[CardInput], output: EngineOutput) -> None:
        drafts = parse_drafts(output.raw, inputs, taxonomy)
        now = clock()
        with open_session() as session:
            for card in inputs:
                item = session.get(Item, card.id)
                if item is None:
                    continue
                draft = drafts.get(card.id)
                store_result(
                    session,
                    item,
                    draft,
                    engine=engine,
                    model=output.model,
                    error=None if draft else "missing or invalid in engine output",
                    now=now,
                    taxonomy=taxonomy,
                    seed=seed,
                )
                if draft:
                    stats.ready += 1
                else:
                    stats.failed += 1

    drive_engines(
        Lane(agy.name, policy.agy_batch, agy.generate, agy.usage) if agy else None,
        Lane(qwen.name, policy.qwen_batch, qwen.generate) if qwen else None,
        policy=policy,
        stats=stats,
        load=load,
        store=store,
        monotonic=monotonic,
    )
    return stats


def record_run(open_session: SessionScope, started_at: datetime, stats: CardRunStats) -> None:
    with open_session() as session:
        session.add(
            CardRun(
                started_at=started_at,
                finished_at=_now(),
                ready=stats.ready,
                failed=stats.failed,
                batches=stats.batches,
                quota=stats.quota,
                note="; ".join(stats.notes)[:2000] or None,
            )
        )
