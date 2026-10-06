from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum
from news_insight.digest.models import DigestStatus


class PeriodicBriefing(Base):
    """An immutable weekly or monthly briefing version built from the period's daily briefings
    (plan 13 C4). `period_end` is exclusive, like every KST calendar window."""

    __tablename__ = "periodic_briefings"
    __table_args__ = (
        UniqueConstraint("kind", "period_key", "version", name="uq_periodic_briefings_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # week | month
    period_key: Mapped[str] = mapped_column(String(10), index=True)  # 2026-W40 | 2026-09
    version: Mapped[int]
    status: Mapped[DigestStatus] = mapped_column(str_enum(DigestStatus))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    days: Mapped[int]  # daily briefings the period had
    model: Mapped[str | None] = mapped_column(String(80))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
