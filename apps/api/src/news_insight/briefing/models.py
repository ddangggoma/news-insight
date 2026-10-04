from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class BriefingStatus(StrEnum):
    PUBLISHED = "published"
    BLOCKED = "blocked"  # a blocking gate failed: the previous published briefing stays current


class BriefingFreeze(Base):
    """04:40 KST snapshot of the day's eligible candidates (D15). One per date."""

    __tablename__ = "briefing_freezes"

    id: Mapped[int] = mapped_column(primary_key=True)
    briefing_date: Mapped[date] = mapped_column(Date, unique=True)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    candidate_ids: Mapped[list[int]] = mapped_column(JSONB)
    taxonomy_revision: Mapped[str] = mapped_column(String(20))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Briefing(Base):
    """An immutable daily briefing version: shortlist + digest + gate results."""

    __tablename__ = "briefings"
    __table_args__ = (
        UniqueConstraint("briefing_date", "version", name="uq_briefings_date_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    briefing_date: Mapped[date] = mapped_column(Date, index=True)
    version: Mapped[int]
    status: Mapped[BriefingStatus] = mapped_column(str_enum(BriefingStatus))
    freeze_id: Mapped[int] = mapped_column(ForeignKey("briefing_freezes.id"))
    digest_id: Mapped[int | None] = mapped_column(ForeignKey("digests.id"))
    input_hash: Mapped[str] = mapped_column(String(64))
    shortlist: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    gates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
