from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class StrategyStatus(StrEnum):
    OK = "ok"  # personas + report written and reviewed
    FAILED = "failed"  # a Claude call failed or returned unusable output


class StrategyRun(Base):
    """Daily persona insights + strategy report (Writer) + independent review (Reviewer)."""

    __tablename__ = "strategy_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    briefing_date: Mapped[date] = mapped_column(Date, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[StrategyStatus] = mapped_column(str_enum(StrategyStatus))
    personas: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    review: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    dropped_claims: Mapped[int] = mapped_column(default=0)
    model: Mapped[str | None] = mapped_column(String(80))
    cost_usd: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
