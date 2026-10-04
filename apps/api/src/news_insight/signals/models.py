from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class RadarSignalSnapshot(Base):
    """One radar card as computed on a day (PRD-1): evidence for the digest and strategy."""

    __tablename__ = "radar_signals"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "period", "window_key", "tone", name="uq_radar_signals"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[str] = mapped_column(String(10))
    window_key: Mapped[str] = mapped_column(String(20))
    is_current: Mapped[bool]
    tone: Mapped[str] = mapped_column(String(10))
    focus_kind: Mapped[str] = mapped_column(String(10))
    focus_key: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
