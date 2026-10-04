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
    MeteredEngine,
    Quota,
    QuotaExhausted,
)
from news_insight.cards.models import CardRun, CardStatus, ItemCard
from news_insight.cards.schemas import CardDraft, CardInput, parse_drafts
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


def store_result(
    session: Session,
    item: Item,
    draft: CardDraft | None,
    *,
    engine: str,
    model: str,
    error: str | None,
    now: datetime,
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


def run_cards(
    open_session: SessionScope,
    *,
    agy: MeteredEngine | None,
    qwen: CardEngine | None,
    policy: CardPolicy,
    clock: Clock = _now,
    monotonic: Callable[[], float] = time.monotonic,
) -> CardRunStats:
    """Generate cards until nothing is pending or the time budget is spent.

    Antigravity is used while its quota allows (D18); when it is spent, unavailable or
    failing, the run continues on local Qwen (user request, 2026-10-04).
    """
    stats = CardRunStats()
    deadline = monotonic() + policy.time_budget_seconds
    use_agy = agy is not None
    quota = Quota(weekly=None, five_hour=None)

    def refresh_quota() -> None:
        nonlocal use_agy, quota
        if agy is None or not use_agy:
            return
        try:
            quota = agy.usage()
        except EngineError as exc:
            stats.notes.append(f"agy usage unavailable: {exc}")
            use_agy = False
            return
        stats.quota = quota.as_dict()
        if not quota.usable(min_weekly=policy.min_weekly, min_five_hour=policy.min_five_hour):
            stats.notes.append(f"agy quota reserved ({quota.as_dict()}): switching to qwen")
            use_agy = False

    refresh_quota()
    while monotonic() < deadline:
        engine: CardEngine | None = agy if use_agy else qwen
        if engine is None:
            stats.notes.append("no engine available")
            break
        size = policy.agy_batch if use_agy else policy.qwen_batch
        with open_session() as session:
            inputs = [
                card_input(item, source) for item, source in pending_items(session, limit=size)
            ]
        if not inputs:
            break
        try:
            output = engine.generate(inputs)
        except QuotaExhausted as exc:
            stats.notes.append(f"{exc}: switching to qwen")
            use_agy = False
            continue
        except EngineError as exc:
            if engine is agy:
                stats.notes.append(f"{exc}: switching to qwen")
                use_agy = False
                continue
            stats.notes.append(str(exc))
            break  # local model down: leave items pending for the next run
        drafts = parse_drafts(output.raw, inputs)
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
                    engine=engine.name,
                    model=output.model,
                    error=None if draft else "missing or invalid in engine output",
                    now=now,
                )
                if draft:
                    stats.ready += 1
                else:
                    stats.failed += 1
        stats.batches[engine.name] = stats.batches.get(engine.name, 0) + 1
        if engine is agy:
            refresh_quota()
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
