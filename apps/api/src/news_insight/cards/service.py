"""Korean card generation: pending selection, engine switching, storage and run records."""

import logging
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from news_insight.cards.engines import (
    CardEngine,
    EngineError,
    EngineOutput,
    MeteredEngine,
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
from news_insight.content.freshness import fresh_condition
from news_insight.content.models import Item
from news_insight.content.normalize import truncate
from news_insight.sources.enums import SourceStatus
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
    return and_(
        fresh_condition(),  # archive pages get no card (2026-10-05 audit)
        or_(
            ItemCard.id.is_(None),
            ItemCard.input_hash != Item.content_hash,
            and_(ItemCard.status == CardStatus.FAILED, ItemCard.attempts < MAX_ATTEMPTS),
        ),
    )


def classify_pending_condition() -> Any:
    """A ready card whose classification predates the current taxonomy revision."""
    return and_(
        ItemCard.status == CardStatus.READY,
        ItemCard.input_hash == Item.content_hash,
        func.coalesce(ItemCard.taxonomy_revision, "") != TAXONOMY_REVISION,
        fresh_condition(),
    )


def pending_items(
    session: Session,
    *,
    limit: int,
    exclude: set[int] | None = None,
    unvalidated_daily_cap: int | None = None,
) -> list[tuple[Item, Source]]:
    """Items needing card text, newest first. With `unvalidated_daily_cap`, a source that is not
    yet active waits once it had that many cards in the last 24 hours, so one unvalidated feed
    cannot spend the day's Antigravity quota (2026-10-05: sitemaps took 83 % of all cards)."""
    conditions = [pending_condition()]
    if exclude:
        conditions.append(Item.id.not_in(exclude))
    if unvalidated_daily_cap is not None:
        busy = (
            select(Item.source_id)
            .join(ItemCard, ItemCard.item_id == Item.id)
            .join(Source, Source.id == Item.source_id)
            .where(
                Source.status != SourceStatus.ACTIVE,
                ItemCard.generated_at >= func.now() - timedelta(hours=24),
            )
            .group_by(Item.source_id)
            .having(func.count() >= unvalidated_daily_cap)
        )
        conditions.append(Item.source_id.not_in(busy))
    statement = (
        select(Item, Source)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .where(*conditions)
        .order_by(Item.first_seen_at.desc(), Item.id.desc())
        .limit(limit)
    )
    return list(session.execute(statement).tuples())


KST = ZoneInfo("Asia/Seoul")


def claude_cards_today(session: Session, now: datetime) -> int:
    """Cards Claude wrote since midnight KST (the scheduled daily cap)."""
    midnight = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.scalar(
            select(func.count())
            .select_from(ItemCard)
            .where(ItemCard.engine == "claude", ItemCard.generated_at >= midnight)
        )
        or 0
    )


def in_quiet_hours(spec: str, now: datetime) -> bool:
    """`spec` is "start-end" in KST hours ("3-11": 03:00 to 10:59); empty means never."""
    try:
        start, end = (int(part) for part in spec.split("-", 1))
    except ValueError:
        return False
    hour = now.astimezone(KST).hour
    return start <= hour < end if start <= end else hour >= start or hour < end


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
    card.companies = draft.companies
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
REUSED = "reuse"
# copied from the donor card: text and classification
_REUSED_FIELDS = (
    "title_ko",
    "summary_ko",
    "keywords",
    "field",
    "themes",
    "signal_type",
    "impact",
    "scope",
    "relevance",
    "topic_candidates",
    "companies",
    "taxonomy_revision",
)


def reuse_cards(session: Session, items: list[Item], *, now: datetime) -> set[int]:
    """Copy the ready card of an item with the same URL or the same content (2026-10-05: 7,465
    URL copies across HN and Europe PMC query sources, 13,192 same-content pages): no engine
    call. Returns the ids that got a card."""
    if not items:
        return set()
    ids = [item.id for item in items]
    rows = session.execute(
        select(Item.canonical_url, Item.content_hash, ItemCard)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .where(
            ItemCard.status == CardStatus.READY,
            Item.id.not_in(ids),
            or_(
                Item.canonical_url.in_({item.canonical_url for item in items}),
                Item.content_hash.in_({item.content_hash for item in items}),
            ),
        )
    ).tuples()
    by_url: dict[str, ItemCard] = {}
    by_hash: dict[str, ItemCard] = {}
    for url, content_hash, row in rows:
        by_url.setdefault(url, row)
        by_hash.setdefault(content_hash, row)
    done: set[int] = set()
    for item in items:
        match = by_url.get(item.canonical_url) or by_hash.get(item.content_hash)
        if match is None:
            continue
        donor = match
        card = session.scalars(select(ItemCard).where(ItemCard.item_id == item.id)).one_or_none()
        if card is None:
            card = ItemCard(item_id=item.id, attempts=0, summary_ko=[], keywords=[])
            session.add(card)
        for name in _REUSED_FIELDS:
            setattr(card, name, getattr(donor, name))
        card.status = CardStatus.READY
        card.engine, card.model = REUSED, f"item:{donor.item_id}"
        card.input_hash, card.generated_at = item.content_hash, now
        card.attempts, card.error, card.classify_attempts = 0, None, 0
        done.add(item.id)
    session.flush()
    return done


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
    reused: int = 0  # copied from a card of the same URL or content
    batches: dict[str, int] = field(default_factory=dict)
    quota: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CardPolicy:
    agy_batch: int = 100
    agy_parallel: int = 3  # independent agy processes per round (quota is the real cap)
    codex_batch: int = 40
    codex_parallel: int = 2
    claude_batch: int = 12
    claude_parallel: int = 3
    codex_classify_batch: int = 100
    qwen_batch: int = 5
    qwen_parallel: int = 1  # Qwen requests at once (LM Studio serves them concurrently)
    classify_batch: int = 200  # classification-only calls carry title, summary and keywords
    qwen_classify_batch: int = 20
    min_weekly: int = 10  # D18: cards may use 90 % of each metered engine's weekly limit
    min_five_hour: int = 2
    time_budget_seconds: float = 540.0
    unvalidated_daily_cap: int | None = 40  # cards per non-active source per 24 hours


@dataclass(frozen=True)
class Job:
    """One engine call: card text for new items, or classification only for re-labelling."""

    kind: str  # "card" | "classify"
    inputs: list[CardInput] | list[ClassifyInput]


FAILED_ROUNDS = 2  # Antigravity rounds in a row where every call failed before giving up


def run_cards(
    open_session: SessionScope,
    *,
    agy: MeteredEngine | None = None,
    qwen: CardEngine | None,
    policy: CardPolicy,
    metered: Sequence[MeteredEngine] | None = None,
    qwen_alongside: bool = False,
    clock: Clock = _now,
    monotonic: Callable[[], float] = time.monotonic,
) -> CardRunStats:
    """Generate cards and reclassify stale ones until nothing is pending or time runs out.

    Metered engines are used in order while each keeps its reserve (D18: `min_weekly` percent of
    the weekly limit is never spent): Codex, then Antigravity (2026-10-05, user request). When
    the last one is spent the run continues on Qwen if it was passed in (`card_qwen_fallback` or
    `--qwen-only`), otherwise items wait for the next run. With `qwen_alongside` Qwen also runs
    `policy.qwen_parallel` lanes next to the metered engine in every round (2026-10-06, user
    request: Qwen full time). A quota error moves to the next engine at once; other failures are
    retried, moving on after FAILED_ROUNDS rounds that all fail (or at once when only Qwen is
    left). Qwen lanes that fail FAILED_ROUNDS rounds in a row stop for the rest of the run.
    While cards wait for a newer taxonomy, one metered lane per round reclassifies them so new
    items are never starved (CLS-2).
    """
    stats = CardRunStats()
    deadline = monotonic() + policy.time_budget_seconds
    chain: list[MeteredEngine] = list(metered) if metered is not None else ([agy] if agy else [])
    at = 0  # index of the metered engine in use; len(chain) once all are spent or down
    fallback = "switching to qwen" if qwen is not None else "waiting for the next run"
    failed_rounds = 0
    qwen_failed_rounds = 0
    qwen_ok = qwen is not None
    attempted: set[int] = set()
    classify_attempted: set[int] = set()

    def advance(reason: str) -> None:
        nonlocal at, failed_rounds
        at += 1
        failed_rounds = 0
        following = chain[at].name if at < len(chain) else None
        stats.notes.append(f"{reason}: {'switching to ' + following if following else fallback}")
        refresh_quota()

    def refresh_quota() -> None:
        nonlocal at
        while at < len(chain):
            engine = chain[at]
            try:
                quota = engine.usage()
            except EngineError as exc:
                stats.notes.append(f"{engine.name} usage unavailable: {exc}")
                at += 1
                continue
            stats.quota = {"engine": engine.name, **quota.as_dict()}
            if quota.usable(min_weekly=policy.min_weekly, min_five_hour=policy.min_five_hour):
                return
            following = chain[at + 1].name if at + 1 < len(chain) else None
            stats.notes.append(
                f"{engine.name} quota reserved ({quota.as_dict()}): "
                + ("switching to " + following if following else fallback)
            )
            at += 1

    refresh_quota()
    while monotonic() < deadline:
        current = chain[at] if at < len(chain) else None
        planned: list[tuple[CardEngine, Job]] = []
        if current is not None:
            jobs = _plan_round(
                open_session, policy, current.name, attempted, classify_attempted, stats
            )
            planned += [(current, job) for job in jobs]
        if qwen is not None and qwen_ok and (current is None or qwen_alongside):
            jobs = _plan_round(open_session, policy, None, attempted, classify_attempted, stats)
            planned += [(qwen, job) for job in jobs]
        if not planned:
            if current is None and not qwen_ok:
                stats.notes.append("no engine available")
            break
        results = _run_pairs(planned)
        exhausted: EngineError | None = None
        metered_results: list[EngineOutput | EngineError] = []
        qwen_results: list[EngineOutput | EngineError] = []
        for (engine, job), result in zip(planned, results, strict=True):
            on_qwen = engine is qwen
            (qwen_results if on_qwen else metered_results).append(result)
            ids = {entry.id for entry in job.inputs}
            if isinstance(result, EngineError):
                (attempted if job.kind == "card" else classify_attempted).difference_update(ids)
                if not on_qwen and (
                    isinstance(result, QuotaExhausted)
                    or (at == len(chain) - 1 and qwen is not None)
                ):
                    exhausted = result
                else:
                    stats.notes.append(str(result))
                continue
            if job.kind == "card":
                _store_batch(open_session, engine.name, job.inputs, result, clock(), stats)  # type: ignore[arg-type]
            else:
                _store_classifications(open_session, job.inputs, result, stats)  # type: ignore[arg-type]
        if qwen_results:
            if all(isinstance(r, EngineError) for r in qwen_results):
                qwen_failed_rounds += 1
                if current is None:
                    break  # Qwen down and nothing else: leave items pending for the next run
                if qwen_failed_rounds >= FAILED_ROUNDS:
                    qwen_ok = False
                    stats.notes.append("qwen lanes stopped for this run after repeated failures")
            else:
                qwen_failed_rounds = 0
        if current is None:
            continue
        if exhausted is not None:
            advance(str(exhausted))
            continue
        if metered_results and all(isinstance(r, EngineError) for r in metered_results):
            failed_rounds += 1
            if failed_rounds >= FAILED_ROUNDS:
                if at == len(chain) - 1:
                    if not qwen_ok:
                        break  # the last metered engine is down: wait for the next run
                    at = len(chain)  # Qwen carries on alone
                    continue
                advance(f"{current.name} failed {failed_rounds} rounds")
                continue
        else:
            failed_rounds = 0
        refresh_quota()
    return stats


def _plan_round(
    open_session: SessionScope,
    policy: CardPolicy,
    metered: str | None,
    attempted: set[int],
    classify_attempted: set[int],
    stats: "CardRunStats | None" = None,
) -> list[Job]:
    """One round of jobs for the metered engine `metered` (by name), or Qwen when None."""
    if metered == "codex":
        lanes, batch = max(1, policy.codex_parallel), policy.codex_batch
        classify_batch = policy.codex_classify_batch
    elif metered == "claude":
        lanes, batch = max(1, policy.claude_parallel), policy.claude_batch
        classify_batch = policy.claude_batch * 3
    elif metered is not None:
        lanes, batch, classify_batch = (
            max(1, policy.agy_parallel),
            policy.agy_batch,
            policy.classify_batch,
        )
    else:
        lanes, batch = max(1, policy.qwen_parallel), policy.qwen_batch
        classify_batch = policy.qwen_classify_batch
    with open_session() as session:
        stale = classify_pending_items(
            session, limit=classify_batch * lanes, exclude=classify_attempted
        )
        # keep one lane for reclassification while new items also wait (metered engines only)
        card_lanes = lanes - 1 if stale and lanes > 1 else lanes
        pending = pending_items(
            session,
            limit=batch * card_lanes,
            exclude=attempted,
            unvalidated_daily_cap=policy.unvalidated_daily_cap,
        )
        reused = reuse_cards(session, [item for item, _ in pending], now=_now())
        if stats is not None:
            stats.reused += len(reused)
        attempted.update(reused)
        pending = [(item, source) for item, source in pending if item.id not in reused]
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


def _run_pairs(planned: list[tuple[CardEngine, Job]]) -> list[EngineOutput | EngineError]:
    """Run every (engine, job) of a round at once: metered lanes and Qwen lanes side by side."""

    def one(pair: tuple[CardEngine, Job]) -> EngineOutput | EngineError:
        engine, job = pair
        try:
            if job.kind == "card":
                return engine.generate(job.inputs)  # type: ignore[arg-type]
            return engine.classify(job.inputs)  # type: ignore[arg-type]
        except EngineError as exc:
            return exc

    if len(planned) == 1:
        return [one(planned[0])]
    with ThreadPoolExecutor(max_workers=len(planned)) as pool:
        return list(pool.map(one, planned))


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
            "reused": stats.reused,
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
