from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class SpotlightStatus(StrEnum):
    PUBLISHED = "published"
    FAILED = "failed"  # the writer or its checks failed: the previous published day stays current


class SpotlightFreeze(Base):
    """Snapshot of the day's per-section candidates (with their stats) the writer chooses from.
    One per date."""

    __tablename__ = "spotlight_freezes"

    id: Mapped[int] = mapped_column(primary_key=True)
    spotlight_date: Mapped[date] = mapped_column(Date, unique=True)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    candidates: Mapped[dict[str, list[dict[str, Any]]]] = mapped_column(JSONB)


class Spotlight(Base):
    """One day's spotlight: the Opus-written headline and benchmark note. One per date."""

    __tablename__ = "spotlights"

    id: Mapped[int] = mapped_column(primary_key=True)
    spotlight_date: Mapped[date] = mapped_column(Date, unique=True)
    status: Mapped[SpotlightStatus] = mapped_column(str_enum(SpotlightStatus))
    model: Mapped[str] = mapped_column(String(80))
    cost_usd: Mapped[float | None] = mapped_column(Float)
    headline: Mapped[str] = mapped_column(Text)
    benchmark_note: Mapped[str] = mapped_column(Text)
    freeze_id: Mapped[int] = mapped_column(ForeignKey("spotlight_freezes.id"))
    error: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SpotlightGroup(StrEnum):
    NOW = "now"  # the day's 24 h window
    SUSTAINED = "sustained"  # attention that lasted several of the last seven days


class SpotlightEntry(Base):
    """One ranked row of a section's list: `rank` is the writer's within its group (최근 24시간
    or 지속 주목), `stat_rank` the statistical."""

    __tablename__ = "spotlight_entries"
    __table_args__ = (
        UniqueConstraint(
            "spotlight_id", "section", "group", "rank", name="uq_spotlight_entries_rank"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    spotlight_id: Mapped[int] = mapped_column(ForeignKey("spotlights.id", ondelete="CASCADE"))
    section: Mapped[str] = mapped_column(String(20))
    rank: Mapped[int]
    stat_rank: Mapped[int]
    key: Mapped[str] = mapped_column(String(200))
    item_ids: Mapped[list[int]] = mapped_column(JSONB)
    title_ko: Mapped[str] = mapped_column(Text)
    product_name: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    why_hot: Mapped[str] = mapped_column(Text)
    rank_note: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    fallback: Mapped[bool] = mapped_column(default=False)
    group: Mapped[str] = mapped_column(String(20), default=SpotlightGroup.NOW, server_default="now")
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")  # Opus's
    signals: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")  # server's
    field: Mapped[str | None] = mapped_column(String(40))  # technology field of the lead card
