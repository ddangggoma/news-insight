from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class DigestStatus(StrEnum):
    PUBLISHED = "published"  # Claude output that passed evidence validation
    FALLBACK = "fallback"  # rule-based digest (Claude failed, rejected, or no items)


class Digest(Base):
    """One immutable daily digest version; re-runs with new input add a version."""

    __tablename__ = "digests"
    __table_args__ = (UniqueConstraint("digest_date", "version", name="uq_digests_date_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_date: Mapped[date] = mapped_column(Date, index=True)
    version: Mapped[int]
    status: Mapped[DigestStatus] = mapped_column(str_enum(DigestStatus))
    model: Mapped[str | None] = mapped_column(String(80))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    item_count: Mapped[int]
    input_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
