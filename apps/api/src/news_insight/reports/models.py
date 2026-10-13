from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class TrendReport(Base):
    """A trend report a reader asked for on a topic (plan 17 R1). The web queues it; the host
    job (launchd, where the Claude CLI is logged in) plans the search, gathers the cards,
    writes the report with Claude Opus and stores it as HTML. Shared by the team."""

    __tablename__ = "trend_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(200))
    brief: Mapped[str | None] = mapped_column(Text)  # what the reader already knows or wants
    days: Mapped[int] = mapped_column(Integer)  # evidence window
    dossier_id: Mapped[int | None] = mapped_column(ForeignKey("dossiers.id", ondelete="SET NULL"))
    # queued → running → ready | failed; archived hides it
    status: Mapped[str] = mapped_column(String(20), index=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # search plan (keywords, …)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # validated report sections
    # evidence (item id → title, url, source, date) and the statistics the report drew on
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    html: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(80))
    cost_usd: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
