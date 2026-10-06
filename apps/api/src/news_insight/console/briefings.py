"""Console read models for daily briefings (P6)."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingFreeze, BriefingStatus
from news_insight.briefing.service import current_briefing, failing
from news_insight.console.cards import card_views
from news_insight.console.schemas import CardView
from news_insight.content.models import Item
from news_insight.digest import service as digest_service
from news_insight.digest.models import Digest
from news_insight.digest.schemas import DigestItemRef, DigestOut
from news_insight.sources.models import Source
from news_insight.strategy.models import StrategyRun
from news_insight.strategy.personas import PERSONAS
from news_insight.strategy.schemas import StrategyReport, number_claims


class GateOut(BaseModel):
    name: str
    label: str
    value: float
    threshold: float
    passed: bool
    blocking: bool


class BriefingSection(BaseModel):
    track: str
    items: list[CardView]


class PersonaOut(BaseModel):
    key: str
    name: str
    group: str
    status: str
    headline: str
    insight: str
    actions: list[str]
    item_ids: list[int]
    relevance: int = 0
    stances: list[dict[str, str]] = []


class StrategyOut(BaseModel):
    status: str
    personas: list[PersonaOut]
    report: dict[str, Any] | None
    review: dict[str, Any] | None
    dropped_claims: int
    error: str | None
    cost_usd: float | None
    items: list[DigestItemRef]


class BriefingOut(BaseModel):
    briefing_date: date
    version: int
    status: BriefingStatus
    published_at: datetime
    frozen_at: datetime
    candidates: int
    gates: list[GateOut]
    failing: list[str]
    sections: list[BriefingSection]
    digest: DigestOut | None
    strategy: StrategyOut | None = None
    is_current: bool
    current_date: date | None


class BriefingSummary(BaseModel):
    briefing_date: date
    version: int
    status: BriefingStatus
    shortlist: int
    failing: list[str]
    published_at: datetime


def briefing_out(session: Session, briefing: Briefing) -> BriefingOut:
    freeze = session.get(BriefingFreeze, briefing.freeze_id)
    ids = [int(entry["item_id"]) for entry in briefing.shortlist]
    views = card_views(session, ids)
    sections: dict[str, list[CardView]] = {}
    for entry in briefing.shortlist:
        view = views.get(int(entry["item_id"]))
        if view is not None:
            sections.setdefault(str(entry["track"]), []).append(view)
    digest = session.get(Digest, briefing.digest_id) if briefing.digest_id else None
    run = session.get(StrategyRun, briefing.strategy_id) if briefing.strategy_id else None
    current = current_briefing(session)
    return BriefingOut(
        briefing_date=briefing.briefing_date,
        version=briefing.version,
        status=briefing.status,
        published_at=briefing.published_at,
        frozen_at=freeze.frozen_at if freeze else briefing.published_at,
        candidates=len(freeze.candidate_ids) if freeze else 0,
        gates=[GateOut.model_validate(gate) for gate in briefing.gates],
        failing=failing(briefing.gates),
        sections=[BriefingSection(track=track, items=items) for track, items in sections.items()],
        digest=digest_service.digest_out(session, digest) if digest is not None else None,
        strategy=strategy_out(session, run) if run is not None else None,
        is_current=current is not None and current.id == briefing.id,
        current_date=current.briefing_date if current else None,
    )


def strategy_out(session: Session, run: StrategyRun) -> StrategyOut:
    names = {p.key: p for p in PERSONAS}
    personas = [
        PersonaOut(
            key=str(p["key"]),
            name=names[p["key"]].name if p["key"] in names else str(p["key"]),
            group=names[p["key"]].group if p["key"] in names else "domain",
            status=str(p["status"]),
            headline=str(p.get("headline") or ""),
            insight=str(p.get("insight") or ""),
            actions=list(p.get("actions") or []),
            item_ids=list(p.get("item_ids") or []),
            relevance=int(p.get("relevance") or 0),
            stances=list(p.get("stances") or []),
        )
        for p in run.personas
    ]
    ids: set[int] = {i for p in personas for i in p.item_ids}
    if run.report:
        report = StrategyReport.model_validate(run.report)
        for claim in number_claims(report):
            ids.update(claim.item_ids)
    refs = [
        DigestItemRef(
            id=item.id, title=item.title, url=item.url, source_name=source.name, track=item.track
        )
        for item, source in session.execute(
            select(Item, Source).join(Source, Source.id == Item.source_id).where(Item.id.in_(ids))
        ).tuples()
    ]
    return StrategyOut(
        status=run.status.value,
        personas=personas,
        report=run.report,
        review=run.review,
        dropped_claims=run.dropped_claims,
        error=run.error,
        cost_usd=run.cost_usd,
        items=refs,
    )


def latest(session: Session) -> Briefing | None:
    return session.scalars(
        select(Briefing).order_by(Briefing.briefing_date.desc(), Briefing.version.desc()).limit(1)
    ).first()


def for_date(session: Session, briefing_date: date) -> Briefing | None:
    return session.scalars(
        select(Briefing)
        .where(Briefing.briefing_date == briefing_date)
        .order_by(Briefing.version.desc())
        .limit(1)
    ).first()


def summaries(session: Session, *, limit: int) -> list[BriefingSummary]:
    rows = session.scalars(
        select(Briefing)
        .order_by(Briefing.briefing_date.desc(), Briefing.version.desc())
        .limit(limit)
    )
    return [
        BriefingSummary(
            briefing_date=b.briefing_date,
            version=b.version,
            status=b.status,
            shortlist=len(b.shortlist),
            failing=failing(b.gates),
            published_at=b.published_at,
        )
        for b in rows
    ]
