"""Console read models for daily briefings (P6)."""

from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingFreeze, BriefingStatus
from news_insight.briefing.service import current_briefing, failing
from news_insight.console.cards import card_views
from news_insight.console.schemas import CardView
from news_insight.digest import service as digest_service
from news_insight.digest.models import Digest
from news_insight.digest.schemas import DigestOut


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
        is_current=current is not None and current.id == briefing.id,
        current_date=current.briefing_date if current else None,
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
