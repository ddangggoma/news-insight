"""Korean card generation: pending selection, engine switching, storage and run records."""

import logging
import math
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, func, not_, or_, select, text, true
from sqlalchemy.orm import Session, aliased

from news_insight.cards.engines import (
    CardEngine,
    EngineError,
    EngineOutput,
    MeteredEngine,
    QuotaExhausted,
)
from news_insight.cards.models import CardRun, CardStatus, ItemCard, ItemTriage
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
from news_insight.content.models import Item, ItemDedup
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


def waits_for_root() -> Any:
    """The item repeats an earlier one (content/duplicates.py) that will get a card: it takes
    a copy of that card instead of an engine call. A root in a paused or retired source, or one
    whose card gave up, does not hold its repeats back."""
    root, root_source, root_card = aliased(Item), aliased(Source), aliased(ItemCard)
    return exists(
        select(ItemDedup.item_id)
        .join(root, root.id == ItemDedup.duplicate_of)
        .join(root_source, root_source.id == root.source_id)
        .outerjoin(root_card, root_card.item_id == root.id)
        .where(
            ItemDedup.item_id == Item.id,
            root_source.status.not_in((SourceStatus.PAUSED, SourceStatus.RETIRED)),
            or_(
                root_card.id.is_(None),
                root_card.status != CardStatus.FAILED,
                root_card.attempts < MAX_ATTEMPTS,
            ),
        )
    )


def pending_condition() -> Any:
    """Card text is needed: no card yet, the item changed since its card, or a failed card
    with retries left. A taxonomy revision alone does not regenerate text (checklist CLS-2).
    Repeats of another item wait for its card (duplicate removal comes before carding)."""
    return and_(
        fresh_condition(),  # archive pages get no card (2026-10-05 audit)
        or_(
            ItemCard.id.is_(None),
            ItemCard.input_hash != Item.content_hash,
            and_(ItemCard.status == CardStatus.FAILED, ItemCard.attempts < MAX_ATTEMPTS),
        ),
        not_(waits_for_root()),
    )


def classify_pending_condition() -> Any:
    """A ready card whose classification predates the current taxonomy revision."""
    return and_(
        ItemCard.status == CardStatus.READY,
        ItemCard.input_hash == Item.content_hash,
        func.coalesce(ItemCard.taxonomy_revision, "") != TAXONOMY_REVISION,
        fresh_condition(),
    )


EXPLORE_SHARE = 0.1  # newest-first picks next to the score order (keeps training labels unbiased)
# a triage probability that may pass the unvalidated-source daily cap: 0.5 since 2026-10-10
# (Mastodon cards scored 0.5-0.8 turned out DX-related 89 % of the time, >= 0.8: 96 %)
CAP_BYPASS_DX = 0.5


def pending_items(
    session: Session,
    *,
    limit: int,
    exclude: set[int] | None = None,
    unvalidated_daily_cap: int | None = None,
    cap_bypass_dx: float = CAP_BYPASS_DX,
) -> list[tuple[Item, Source]]:
    """Items needing card text, by triage score (plan 16 #3) with a newest-first share.

    Paused and retired sources wait for good, and so do items on a node the reader excluded
    (triage weight 0). With `unvalidated_daily_cap`, a source that is not yet active waits once
    it had that many cards in the last 24 hours (2026-10-05: sitemaps took 83 % of all cards),
    unless triage gives the item a high DX probability."""
    conditions = [
        pending_condition(),
        Source.status.not_in((SourceStatus.PAUSED, SourceStatus.RETIRED)),
        or_(ItemTriage.item_id.is_(None), ItemTriage.weight > 0),
    ]
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
        conditions.append(
            or_(
                Item.source_id.not_in(busy),
                func.coalesce(ItemTriage.dx_probability, 0) >= cap_bypass_dx,
            )
        )
    base = (
        select(Item, Source)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .outerjoin(ItemTriage, ItemTriage.item_id == Item.id)
        .where(*conditions)
    )
    ranked_limit = max(1, math.ceil(limit * (1 - EXPLORE_SHARE))) if limit > 1 else limit
    ranked = list(
        session.execute(
            base.order_by(
                ItemTriage.score.desc().nulls_last(), Item.first_seen_at.desc(), Item.id.desc()
            ).limit(ranked_limit)
        ).tuples()
    )
    taken = {item.id for item, _ in ranked}
    rest = limit - len(ranked)
    newest = (
        list(
            session.execute(
                base.where(Item.id.not_in(taken) if taken else true())
                .order_by(Item.first_seen_at.desc(), Item.id.desc())
                .limit(rest)
            ).tuples()
        )
        if rest > 0
        else []
    )
    return ranked + newest


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
    card.extra_labels = draft.labels
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


# members of duplicate groups that lack a current card, each with the member to copy from:
# the root when it has a card, otherwise the earliest member that has one
_DONORS = text(
    """
    with rep as (
      select item_id, duplicate_of as root from item_dedup where duplicate_of is not null
    ), grp as (
      select item_id, root from rep
      union
      select root, root from rep
    )
    select distinct on (t.item_id) t.item_id, donor.item_id as donor_id
    from grp t
    join items i on i.id = t.item_id
    left join item_cards own on own.item_id = t.item_id
    join grp donor on donor.root = t.root and donor.item_id <> t.item_id
    join items di on di.id = donor.item_id
    join item_cards dc on dc.item_id = donor.item_id
    where dc.status = 'ready' and dc.input_hash = di.content_hash
      and (i.published_at is null or i.published_at >= i.first_seen_at - interval '30 days')
      and (own.id is null or own.input_hash <> i.content_hash or own.status = 'failed')
    order by t.item_id, (donor.item_id = t.root) desc, donor.item_id
    limit :limit
    """
)


def reuse_cards(session: Session, *, now: datetime, limit: int = 5000) -> set[int]:
    """Copy a card within a duplicate group (content/duplicates.py): every member without a
    current card takes the root's card, or another member's when the root has none yet. No
    engine call. Returns the ids that got a card."""
    pairs = session.execute(_DONORS, {"limit": limit}).tuples().all()
    if not pairs:
        return set()
    donors = {
        card.item_id: card
        for card in session.scalars(
            select(ItemCard).where(ItemCard.item_id.in_({donor for _, donor in pairs}))
        )
    }
    items = {
        item.id: item
        for item in session.scalars(select(Item).where(Item.id.in_({t for t, _ in pairs})))
    }
    own = {
        card.item_id: card
        for card in session.scalars(select(ItemCard).where(ItemCard.item_id.in_(list(items))))
    }
    done: set[int] = set()
    for target, donor_id in pairs:
        donor, item = donors[donor_id], items[target]
        card = own.get(target)
        if card is None:
            card = ItemCard(item_id=target, attempts=0, summary_ko=[], keywords=[])
            session.add(card)
        for name in _REUSED_FIELDS:
            setattr(card, name, getattr(donor, name))
        card.status = CardStatus.READY
        card.engine, card.model = REUSED, f"item:{donor.item_id}"
        card.input_hash, card.generated_at = item.content_hash, now
        card.attempts, card.error, card.classify_attempts = 0, None, 0
        done.add(target)
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
    cap_bypass_dx: float = CAP_BYPASS_DX  # triage probability that passes that cap


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
    retried, moving on after FAILED_ROUNDS rounds in a row in which every lane failed; a round
    where some lanes work resets the count. Qwen lanes that fail FAILED_ROUNDS rounds in a row
    stop for the rest of the run.
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
                # only a spent quota moves on at once; any other failure of one lane is retried
                # (2026-10-10: one malformed answer among 3-6 lanes dropped Antigravity for the
                # rest of the run, so whole runs fell back to Qwen)
                if not on_qwen and isinstance(result, QuotaExhausted):
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
        # repeats take their group's card first; the queue then holds one item per story
        reused = reuse_cards(session, now=_now())
        if stats is not None:
            stats.reused += len(reused)
        pending = pending_items(
            session,
            limit=batch * card_lanes,
            exclude=attempted,
            unvalidated_daily_cap=policy.unvalidated_daily_cap,
            cap_bypass_dx=policy.cap_bypass_dx,
        )
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
