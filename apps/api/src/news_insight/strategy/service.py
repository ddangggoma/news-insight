"""Persona insights, strategy Writer and independent Reviewer on the frozen shortlist (§7, D14)."""

import hashlib
import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.content.models import Item
from news_insight.digest.claude import ClaudeClient, ClaudeError
from news_insight.sources.models import Source
from news_insight.stories.models import StoryItem
from news_insight.strategy.models import StrategyRun, StrategyStatus
from news_insight.strategy.personas import PERSONA_REVISION, PERSONAS
from news_insight.strategy.prompts import (
    COMMON_RULES,
    PERSONA_INSTRUCTION,
    REVIEWER_INSTRUCTION,
    WRITER_INSTRUCTION,
)
from news_insight.strategy.schemas import (
    PERSONA_SCHEMA,
    REPORT_SCHEMA,
    REVIEW_SCHEMA,
    Review,
    apply_review,
    claim_count,
    validate_personas,
    validate_report,
)


def _evidence(session: Session, item_ids: list[int]) -> tuple[list[dict[str, Any]], dict[int, int]]:
    rows = list(
        session.execute(
            select(Item, Source, ItemCard, StoryItem.story_id)
            .join(Source, Source.id == Item.source_id)
            .join(ItemCard, ItemCard.item_id == Item.id)
            .outerjoin(StoryItem, StoryItem.item_id == Item.id)
            .where(Item.id.in_(item_ids))
        ).tuples()
    )
    story_of = {
        item.id: (story_id if story_id is not None else -item.id) for item, _, _, story_id in rows
    }
    payload = [
        {
            "id": item.id,
            "story": story_of[item.id],
            "title": card.title_ko or item.title,
            "summary": " ".join(card.summary_ko)[:300],
            "source": source.name,
            "track": item.track.value,
            "field": card.field,
            "themes": list(card.themes or []),
            "signal_type": card.signal_type,
            "impact": card.impact,
        }
        for item, source, card, _ in rows
    ]
    return payload, story_of


def latest_for(session: Session, briefing_date: date) -> StrategyRun | None:
    return session.scalars(
        select(StrategyRun)
        .where(StrategyRun.briefing_date == briefing_date)
        .order_by(StrategyRun.id.desc())
        .limit(1)
    ).first()


def generate_strategy(
    session: Session,
    *,
    briefing_date: date,
    item_ids: list[int],
    now: datetime,
    client: ClaudeClient,
    model: str,
) -> StrategyRun:
    input_hash = hashlib.sha256(
        json.dumps({"ids": sorted(item_ids), "personas": PERSONA_REVISION}).encode()
    ).hexdigest()
    existing = session.scalars(
        select(StrategyRun).where(
            StrategyRun.briefing_date == briefing_date,
            StrategyRun.input_hash == input_hash,
            StrategyRun.status == StrategyStatus.OK,
        )
    ).first()
    if existing is not None:
        return existing
    items, story_of = _evidence(session, item_ids)
    run = StrategyRun(
        briefing_date=briefing_date,
        input_hash=input_hash,
        status=StrategyStatus.FAILED,
        personas=[],
        created_at=now,
    )
    cost = 0.0
    try:
        roster = [{"key": p.key, "name": p.name, "focus": p.focus} for p in PERSONAS]
        persona_result = client.generate(
            {"personas": roster, "items": items},
            schema=PERSONA_SCHEMA,
            model=model,
            system=COMMON_RULES,
            instruction=PERSONA_INSTRUCTION,
        )
        cost += persona_result.cost_usd
        run.personas = [
            p.model_dump() for p in validate_personas(persona_result.structured, story_of)
        ]
        writer = client.generate(
            {"items": items},
            schema=REPORT_SCHEMA,
            model=model,
            system=COMMON_RULES,
            instruction=WRITER_INSTRUCTION,
        )
        cost += writer.cost_usd
        report = validate_report(writer.structured, story_of)
        if report is None:
            raise ClaudeError("strategy report failed validation")
        reviewer = client.generate(
            {"report": report.model_dump(), "items": items},
            schema=REVIEW_SCHEMA,
            model=model,
            system=COMMON_RULES,
            instruction=REVIEWER_INSTRUCTION,
        )
        cost += reviewer.cost_usd
        review = Review.model_validate(reviewer.structured)
        report, dropped = apply_review(report, review)
        run.report = report.model_dump()
        run.review = review.model_dump()
        run.dropped_claims = dropped
        run.model = writer.model
        run.status = StrategyStatus.OK
    except (ClaudeError, ValueError) as exc:
        run.error = str(exc)[:1000]
    run.cost_usd = cost or None
    session.add(run)
    session.flush()
    return run


def strategy_ok(run: StrategyRun | None, *, min_claims: int = 3) -> tuple[bool, bool]:
    """(personas complete, strategy claims sufficient after review)."""
    if run is None or run.status is not StrategyStatus.OK or run.report is None:
        return False, False
    from news_insight.strategy.schemas import StrategyReport

    personas_ok = len(run.personas) == len(PERSONAS)
    return personas_ok, claim_count(StrategyReport.model_validate(run.report)) >= min_claims
