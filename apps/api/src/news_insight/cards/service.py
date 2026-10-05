"""Korean card generation: pending selection, engine switching, storage and run records."""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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
    QuotaExhausted,
)
from news_insight.cards.models import CardRun, CardStatus, ItemCard
from news_insight.cards.preserve import missing_facts
from news_insight.cards.schemas import (
    CardDraft,
    CardInput,
    Classification,
    ClassifyInput,
    parse_classifications,
    parse_drafts,
)
from news_insight.content.models import Item
from news_insight.content.normalize import truncate
from news_insight.sources.models import Source
from news_insight.taxonomy.catalog import TAXONOMY_REVISION

MAX_ATTEMPTS = 3
MAX_CLASSIFY_ATTEMPTS = 3
EXCERPT_LIMIT = 500
SessionScope = Callable[[], AbstractContextManager[Session]]
Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(UTC)


def pending_condition() -> Any:
    """Card text is needed: no card yet, the item changed since its card, or a failed card
    with retries left. A taxonomy revision alone does not regenerate text (checklist CLS-2)."""
    return or_(
        ItemCard.id.is_(None),
        ItemCard.input_hash != Item.content_hash,
        and_(ItemCard.status == CardStatus.FAILED, ItemCard.attempts < MAX_ATTEMPTS),
    )


def classify_pending_condition() -> Any:
    """A ready card whose classification predates the current taxonomy revision."""
    return and_(
        ItemCard.status == CardStatus.READY,
        ItemCard.input_hash == Item.content_hash,
        func.coalesce(ItemCard.taxonomy_revision, "") != TAXONOMY_REVISION,
    )


def pending_items(
    session: Session, *, limit: int, exclude: set[int] | None = None
) -> list[tuple[Item, Source]]:
    conditions = [pending_condition()]
    if exclude:
        conditions.append(Item.id.not_in(exclude))
    statement = (
        select(Item, Source)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .where(*conditions)
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


def classify_pending_items(
    session: Session, *, limit: int, exclude: set[int] | None = None
) -> list[tuple[Item, ItemCard]]:
    conditions = [classify_pending_condition()]
    if exclude:
        conditions.append(Item.id.not_in(exclude))
    statement = (
        select(Item, ItemCard)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .where(*conditions)
        .order_by(Item.first_seen_at.desc(), Item.id.desc())
        .limit(limit)
    )
    return list(session.execute(statement).tuples())


def classify_pending_count(session: Session) -> int:
    statement = (
        select(func.count())
        .select_from(Item)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .where(classify_pending_condition())
    )
    return session.scalar(statement) or 0


def classify_input(item: Item, card: ItemCard) -> ClassifyInput:
    return ClassifyInput(
        id=item.id,
        title=item.title,
        title_ko=card.title_ko or item.title,
        summary_ko=list(card.summary_ko),
        keywords=list(card.keywords),
    )


def _apply_classification(card: ItemCard, draft: Classification) -> None:
    card.field, card.themes, card.signal_type = draft.field, draft.themes, draft.signal_type
    card.businesses = []  # taxonomy v2 has no business axis (column dropped after reclassification)
    card.impact, card.scope, card.relevance = draft.impact, draft.scope, draft.relevance
    card.topic_candidates = draft.topic_candidates
    card.taxonomy_revision = TAXONOMY_REVISION
    card.classify_attempts = 0


def store_classification(
    session: Session, card: ItemCard, draft: Classification | None, *, error: str | None
) -> bool:
    """Reclassify a card in place; the card text never changes. After MAX_CLASSIFY_ATTEMPTS
    failures the card is marked current with empty labels so it stops blocking the lane."""
    if draft is not None:
        _apply_classification(card, draft)
        session.flush()
        return True
    card.classify_attempts += 1
    if card.classify_attempts >= MAX_CLASSIFY_ATTEMPTS:
        card.field, card.themes, card.signal_type = None, [], None
        card.impact, card.topic_candidates = None, []
        card.taxonomy_revision = TAXONOMY_REVISION
        card.classify_attempts = 0
        card.error = f"classification gave up: {error}"[:500]
    session.flush()
    return False


def card_input(item: Item, source: Source, keep: list[str] | None = None) -> CardInput:
    excerpt = item.summary or item.body
    return CardInput(
        id=item.id,
        title=item.title,
        source=source.name,
        language=source.language,
        excerpt=truncate(excerpt, EXCERPT_LIMIT) if excerpt else None,
        keep=keep or None,
    )


LOST = "preservation: lost "


def lost_facts(session: Session, item_ids: list[int]) -> dict[int, list[str]]:
    """Facts the previous attempt dropped, for items being retried on the same content."""
    if not item_ids:
        return {}
    rows = session.execute(
        select(ItemCard.item_id, ItemCard.error)
        .join(Item, Item.id == ItemCard.item_id)
        .where(
            ItemCard.item_id.in_(item_ids),
            ItemCard.error.like(f"{LOST}%"),
            ItemCard.input_hash == Item.content_hash,
        )
    ).tuples()
    return {
        item_id: [part.strip() for part in error.removeprefix(LOST).split(",") if part.strip()]
        for item_id, error in rows
        if error
    }


def store_result(
    session: Session,
    item: Item,
    draft: CardDraft | None,
    *,
    engine: str,
    model: str,
    error: str | None,
    now: datetime,
    note: str | None = None,
) -> ItemCard:
    """Store a draft (or a failure). `note` stays on a ready card: a fact the last attempt still
    lost, kept visible to the console instead of hiding the item."""
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
        _apply_classification(card, draft)
        card.attempts, card.error = 0, note
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
    classified: int = 0
    classify_failed: int = 0
    soft: int = 0  # kept on the last attempt although a fact was lost
    batches: dict[str, int] = field(default_factory=dict)
    quota: dict[str, int | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CardPolicy:
    agy_batch: int = 100
    agy_parallel: int = 3  # independent agy processes per round (quota is the real cap)
    qwen_batch: int = 5
    classify_batch: int = 200  # classification-only calls carry title, summary and keywords
    qwen_classify_batch: int = 20
    min_weekly: int = 10  # D18: cards may use 90 % of the weekly Antigravity limit
    min_five_hour: int = 2
    time_budget_seconds: float = 540.0


@dataclass(frozen=True)
class Job:
    """One engine call: card text for new items, or classification only for re-labelling."""

    kind: str  # "card" | "classify"
    inputs: list[CardInput] | list[ClassifyInput]


FAILED_ROUNDS = 2  # Antigravity rounds in a row where every call failed before giving up


def run_cards(
    open_session: SessionScope,
    *,
    agy: MeteredEngine | None,
    qwen: CardEngine | None,
    policy: CardPolicy,
    clock: Clock = _now,
    monotonic: Callable[[], float] = time.monotonic,
) -> CardRunStats:
    """Generate cards and reclassify stale ones until nothing is pending or time runs out.

    Antigravity is used while its quota allows (D18). Without a Qwen engine (the default since
    2026-10-05, user request) a spent quota ends the run until the next one, and a failed batch
    is retried later while the run goes on, stopping after FAILED_ROUNDS rounds that all fail.
    With Qwen passed in (`card_qwen_fallback` or `--qwen-only`) the run continues there.
    While cards wait for a newer taxonomy, one Antigravity lane per round reclassifies them
    so new items are never starved (checklist CLS-2). On Qwen, reclassification waits for new items.
    """
    stats = CardRunStats()
    deadline = monotonic() + policy.time_budget_seconds
    use_agy = agy is not None
    fallback = "switching to qwen" if qwen is not None else "waiting for the next run"
    failed_rounds = 0
    attempted: set[int] = set()
    classify_attempted: set[int] = set()
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
            stats.notes.append(f"agy quota reserved ({quota.as_dict()}): {fallback}")
            use_agy = False

    refresh_quota()
    while monotonic() < deadline:
        engine: CardEngine | None = agy if use_agy else qwen
        if engine is None:
            stats.notes.append("no engine available")
            break
        jobs = _plan_round(open_session, policy, use_agy, attempted, classify_attempted)
        if not jobs:
            break
        results = _run_jobs(engine, jobs)
        switch = False
        for job, result in zip(jobs, results, strict=True):
            ids = {entry.id for entry in job.inputs}
            if isinstance(result, EngineError):
                (attempted if job.kind == "card" else classify_attempted).difference_update(ids)
            if isinstance(result, QuotaExhausted) or (
                isinstance(result, EngineError) and engine is agy and qwen is not None
            ):
                stats.notes.append(f"{result}: {fallback}")
                switch = True
                continue
            if isinstance(result, EngineError):
                stats.notes.append(str(result))
                continue
            if job.kind == "card":
                _store_batch(open_session, engine.name, job.inputs, result, clock(), stats)  # type: ignore[arg-type]
            else:
                _store_classifications(open_session, job.inputs, result, stats)  # type: ignore[arg-type]
        if switch:
            use_agy = False
            continue
        if all(isinstance(r, EngineError) for r in results):
            failed_rounds += 1
            if engine is not agy or failed_rounds >= FAILED_ROUNDS:
                break  # engine down: leave items pending for the next run
        else:
            failed_rounds = 0
        if engine is agy:
            refresh_quota()
    return stats


def _plan_round(
    open_session: SessionScope,
    policy: CardPolicy,
    use_agy: bool,
    attempted: set[int],
    classify_attempted: set[int],
) -> list[Job]:
    lanes = max(1, policy.agy_parallel) if use_agy else 1
    batch = policy.agy_batch if use_agy else policy.qwen_batch
    classify_batch = policy.classify_batch if use_agy else policy.qwen_classify_batch
    with open_session() as session:
        stale = classify_pending_items(
            session, limit=classify_batch * lanes, exclude=classify_attempted
        )
        # keep one lane for reclassification while new items also wait (Antigravity only)
        card_lanes = lanes - 1 if stale and lanes > 1 else lanes
        pending = pending_items(session, limit=batch * card_lanes, exclude=attempted)
        keep = lost_facts(session, [item.id for item, _ in pending])
        inputs = [card_input(item, source, keep.get(item.id)) for item, source in pending]
        jobs = [Job("card", inputs[i : i + batch]) for i in range(0, len(inputs), batch)]
        stale_inputs = [classify_input(item, card) for item, card in stale]
        if stale_inputs and not jobs:
            # nothing new to card: every lane reclassifies (a taxonomy revision lands fast)
            jobs = [
                Job("classify", stale_inputs[i : i + classify_batch])
                for i in range(0, len(stale_inputs), classify_batch)
            ]
        elif stale_inputs and lanes > 1:
            jobs.append(Job("classify", stale_inputs[:classify_batch]))
    attempted.update(entry.id for entry in inputs)  # retries wait for the next run
    for job in jobs:
        if job.kind == "classify":
            classify_attempted.update(entry.id for entry in job.inputs)
    return jobs


def _run_jobs(engine: CardEngine, jobs: list[Job]) -> list[EngineOutput | EngineError]:
    def one(job: Job) -> EngineOutput | EngineError:
        try:
            if job.kind == "card":
                return engine.generate(job.inputs)  # type: ignore[arg-type]
            return engine.classify(job.inputs)  # type: ignore[arg-type]
        except EngineError as exc:
            return exc

    if len(jobs) == 1:
        return [one(jobs[0])]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(one, jobs))


def _store_classifications(
    open_session: SessionScope,
    chunk: list[ClassifyInput],
    output: EngineOutput,
    stats: "CardRunStats",
) -> None:
    drafts = parse_classifications(output.raw, chunk)
    with open_session() as session:
        for entry in chunk:
            card = session.scalars(select(ItemCard).where(ItemCard.item_id == entry.id)).first()
            if card is None:
                continue
            draft = drafts.get(entry.id)
            ok = store_classification(
                session, card, draft, error=None if draft else "missing in engine output"
            )
            if ok:
                stats.classified += 1
            else:
                stats.classify_failed += 1


def _store_batch(
    open_session: SessionScope,
    engine_name: str,
    chunk: list[CardInput],
    output: EngineOutput,
    now: datetime,
    stats: "CardRunStats",
) -> None:
    drafts = parse_drafts(output.raw, chunk)
    with open_session() as session:
        for card in chunk:
            item = session.get(Item, card.id)
            if item is None:
                continue
            draft = drafts.get(card.id)
            error = None if draft else "missing or invalid in engine output"
            note = None
            if draft is not None and (lost := missing_facts(card, draft)):
                if _attempts(session, item) + 1 >= MAX_ATTEMPTS:
                    # last try: keep the translation and note the loss rather than hide the item
                    note = f"preservation (kept on last attempt): lost {', '.join(lost)}"
                    stats.soft += 1
                else:
                    draft, error = None, f"{LOST}{', '.join(lost)}"
            store_result(
                session,
                item,
                draft,
                engine=engine_name,
                model=output.model,
                error=error,
                now=now,
                note=note,
            )
            if draft:
                stats.ready += 1
            else:
                stats.failed += 1
    stats.batches[engine_name] = stats.batches.get(engine_name, 0) + 1


def _attempts(session: Session, item: Item) -> int:
    """Failed attempts so far on the item's current content."""
    card = session.scalars(select(ItemCard).where(ItemCard.item_id == item.id)).one_or_none()
    if card is None or card.input_hash != item.content_hash:
        return 0
    return card.attempts


def record_run(open_session: SessionScope, started_at: datetime, stats: CardRunStats) -> None:
    logging.getLogger(__name__).info(
        "card run",
        extra={
            "ready": stats.ready,
            "failed": stats.failed,
            "soft": stats.soft,
            "batches": stats.batches,
            "quota": stats.quota,
            "notes": stats.notes[:5],
        },
    )
    with open_session() as session:
        session.add(
            CardRun(
                started_at=started_at,
                finished_at=_now(),
                ready=stats.ready,
                failed=stats.failed,
                classified=stats.classified,
                batches=stats.batches,
                quota=stats.quota,
                note="; ".join(stats.notes)[:2000] or None,
            )
        )
