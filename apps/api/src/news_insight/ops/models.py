from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class Severity(StrEnum):
    CRITICAL = "critical"  # publication or collection is failing now
    WARNING = "warning"  # degraded; acts on its own soon if ignored
    INFO = "info"


class OpsAlert(Base):
    """One alert episode: opened when a check first fails, resolved when it passes again."""

    __tablename__ = "ops_alerts"
    __table_args__ = (Index("ix_ops_alerts_open", "key", "resolved_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80))
    severity: Mapped[Severity] = mapped_column(str_enum(Severity))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
