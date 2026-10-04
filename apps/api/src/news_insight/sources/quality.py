"""V5 seven-day quality trial and V6 promotion (roadmap D8, P5).

Signals come from the last 7 days of Korean cards: DX relevance (scope dx / dx_dependency)
and translation success. Sources with enough classified items are judged:
- relevance below PAUSE_BELOW → paused (`low DX relevance …`), whatever their stage,
- V4/V5 sources at or above PROMOTE_AT with good translation → V5 passed, then V6 in
  descending relevance order while their track has room (check_quota).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item
from news_insight.sources.enums import SourceStatus, ValidationStage
from news_insight.sources.ladder import CheckResult, pause_source, record_check
from news_insight.sources.models import Source
from news_insight.sources.portfolio import active_portfolio, check_quota

WINDOW = timedelta(days=7)
MIN_CLASSIFIED = 20
PAUSE_BELOW = 0.15
PROMOTE_AT = 0.35
MIN_TRANSLATION = 0.95
RELEVANT_SCOPES = ("dx", "dx_dependency")


@dataclass(frozen=True)
class SourceQuality:
    source_id: int
    items: int
    classified: int
    relevant: int
    ready: int
    failed: int

    @property
    def relevance(self) -> float | None:
        return self.relevant / self.classified if self.classified else None

    @property
    def translation(self) -> float | None:
        done = self.ready + self.failed
        return self.ready / done if done else None


@dataclass
class QualityRun:
    judged: int = 0
    paused: list[str] = field(default_factory=list)
    passed_v5: list[str] = field(default_factory=list)
    promoted_v6: list[str] = field(default_factory=list)
    track_full: list[str] = field(default_factory=list)


def measure(session: Session, *, now: datetime) -> dict[int, SourceQuality]:
    since = now - WINDOW
    ready = ItemCard.status == CardStatus.READY
    rows = session.execute(
        select(
            Item.source_id,
            func.count(Item.id),
            func.count(case((ready & ItemCard.scope.is_not(None), 1))),
            func.count(case((ready & ItemCard.scope.in_(RELEVANT_SCOPES), 1))),
            func.count(case((ready, 1))),
            func.count(case((ItemCard.status == CardStatus.FAILED, 1))),
        )
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .where(Item.first_seen_at >= since)
        .group_by(Item.source_id)
    ).tuples()
    return {
        source_id: SourceQuality(source_id, items, classified, relevant, ok, bad)
        for source_id, items, classified, relevant, ok, bad in rows
    }


def _metrics(quality: SourceQuality) -> dict[str, object]:
    return {
        "items_7d": quality.items,
        "classified_7d": quality.classified,
        "relevance": round(quality.relevance or 0.0, 3),
        "translation": round(quality.translation or 0.0, 3),
    }


def run_quality(session: Session, *, now: datetime, apply: bool = True) -> QualityRun:
    qualities = measure(session, now=now)
    run = QualityRun()
    sources = {
        source.id: source
        for source in session.scalars(
            select(Source).where(
                Source.status.in_([SourceStatus.CANDIDATE, SourceStatus.ACTIVE]),
                Source.id.in_(list(qualities)),
            )
        )
    }
    promotable: list[tuple[float, Source, SourceQuality]] = []
    for source_id, quality in qualities.items():
        source = sources.get(source_id)
        relevance = quality.relevance
        if source is None or relevance is None or quality.classified < MIN_CLASSIFIED:
            continue
        run.judged += 1
        if relevance < PAUSE_BELOW:
            run.paused.append(source.key)
            if apply:
                pause_source(
                    session,
                    source,
                    reason=f"low DX relevance {relevance:.0%} (7d, n={quality.classified})",
                )
            continue
        waiting = source.validation_stage in (ValidationStage.V4, ValidationStage.V5)
        if waiting and relevance >= PROMOTE_AT:
            translation_ok = (quality.translation or 0.0) >= MIN_TRANSLATION
            if translation_ok:
                promotable.append((relevance, source, quality))
    promotable.sort(key=lambda entry: entry[0], reverse=True)
    for _, source, quality in promotable:
        run.passed_v5.append(source.key)
        if not apply:
            continue
        if source.validation_stage is ValidationStage.V4:
            record_check(
                session, source, ValidationStage.V5, CheckResult(True, [], _metrics(quality))
            )
        gate = check_quota(active_portfolio(session), track=source.track, region=source.region)
        record_check(session, source, ValidationStage.V6, gate)
        if gate.passed:
            run.promoted_v6.append(source.key)
        else:
            run.track_full.append(source.key)
    return run
