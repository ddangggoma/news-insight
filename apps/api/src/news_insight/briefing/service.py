"""Daily freeze (04:40) and immutable publication (05:00) with fail-safe (D15, §8)."""

import hashlib
import json
import logging
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.briefing.gates import Gate, evaluate
from news_insight.briefing.models import Briefing, BriefingFreeze, BriefingStatus
from news_insight.briefing.selection import (
    SelectionRules,
    eligible_items,
    load_candidates,
    shortlist,
)
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.digest.claude import ClaudeClient
from news_insight.digest.service import generate_digest
from news_insight.signals import service as radar_signals
from news_insight.stories.models import StoryItem
from news_insight.strategy.service import generate_strategy, strategy_ok
from news_insight.taxonomy.catalog import TAXONOMY_REVISION

DEFAULT_RULES = SelectionRules()


def freeze(session: Session, *, briefing_date: date, now: datetime) -> BriefingFreeze:
    """Snapshot eligible candidates once per date; later calls return the same freeze."""
    existing = session.scalars(
        select(BriefingFreeze).where(BriefingFreeze.briefing_date == briefing_date)
    ).one_or_none()
    if existing is not None:
        return existing
    snapshot = BriefingFreeze(
        briefing_date=briefing_date,
        frozen_at=now,
        candidate_ids=eligible_items(session, briefing_date=briefing_date),
        taxonomy_revision=TAXONOMY_REVISION,
        config={"rules": DEFAULT_RULES.__dict__},
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def current_briefing(session: Session) -> Briefing | None:
    return session.scalars(
        select(Briefing)
        .where(Briefing.status == BriefingStatus.PUBLISHED)
        .order_by(Briefing.briefing_date.desc(), Briefing.version.desc())
        .limit(1)
    ).first()


def publish(
    session: Session,
    *,
    briefing_date: date,
    now: datetime,
    client: ClaudeClient,
    model: str,
    rules: SelectionRules = DEFAULT_RULES,
    with_strategy: bool = True,
) -> Briefing:
    snapshot = freeze(session, briefing_date=briefing_date, now=now)
    selected = shortlist(load_candidates(session, list(snapshot.candidate_ids), now=now), rules)
    ids = [c.item_id for c in selected]
    input_hash = hashlib.sha256(
        json.dumps({"freeze": snapshot.id, "ids": ids}, sort_keys=True).encode()
    ).hexdigest()
    same = session.scalars(
        select(Briefing).where(
            Briefing.briefing_date == briefing_date, Briefing.input_hash == input_hash
        )
    ).first()
    if same is not None:
        return same  # same input: no-op (immutable versions)
    signals = radar_signals.evidence(radar_signals.ensure(session, day=briefing_date, now=now))
    digest = (
        generate_digest(
            session,
            digest_date=briefing_date,
            now=now,
            client=client,
            model=model,
            item_ids=set(ids),
            signals=signals,
        )
        if ids
        else None
    )
    strategy = (
        generate_strategy(
            session,
            briefing_date=briefing_date,
            item_ids=ids,
            now=now,
            client=client,
            model=model,
            signals=signals,
        )
        if ids and with_strategy
        else None
    )
    personas_ok, strategy_passed = strategy_ok(strategy) if with_strategy else (None, None)
    carded = (
        session.scalar(
            select(func.count())
            .select_from(ItemCard)
            .where(ItemCard.item_id.in_(ids), ItemCard.status == CardStatus.READY)
        )
        or 0
    )
    story_ids = dict(
        session.execute(
            select(StoryItem.item_id, StoryItem.story_id).where(StoryItem.item_id.in_(ids))
        )
        .tuples()
        .all()
    )
    gates = evaluate(
        selected,
        rules=rules,
        carded=carded,
        story_ids=story_ids,
        digest=digest,
        personas_ok=personas_ok,
        strategy_ok=strategy_passed,
    )
    blocked = any(g.blocking and not g.passed for g in gates)
    version = (
        session.scalar(
            select(func.max(Briefing.version)).where(Briefing.briefing_date == briefing_date)
        )
        or 0
    ) + 1
    briefing = Briefing(
        briefing_date=briefing_date,
        version=version,
        status=BriefingStatus.BLOCKED if blocked else BriefingStatus.PUBLISHED,
        freeze_id=snapshot.id,
        digest_id=digest.id if digest is not None else None,
        strategy_id=strategy.id if strategy is not None else None,
        input_hash=input_hash,
        shortlist=[
            {"item_id": c.item_id, "track": c.track, "score": round(c.score, 2)} for c in selected
        ],
        gates=[g.as_dict() for g in gates],
        published_at=now,
    )
    session.add(briefing)
    logging.getLogger(__name__).info(
        "briefing published" if briefing.status is BriefingStatus.PUBLISHED else "briefing blocked",
        extra={
            "date": str(briefing_date),
            "version": briefing.version,
            "shortlist": len(briefing.shortlist),
            "failing": failing(briefing.gates),
        },
    )
    session.flush()
    return briefing


def failing(gates: list[dict[str, object]]) -> list[str]:
    return [str(g["label"]) for g in gates if g.get("blocking") and not g.get("passed")]


__all__ = ["Gate", "current_briefing", "failing", "freeze", "publish"]
