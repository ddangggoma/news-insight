from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class AiModel(Base):
    """An AI model the leaderboards rank; `name` is the normalized spelling (benchmarks.names)."""

    __tablename__ = "ai_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    org: Mapped[str | None] = mapped_column(String(80))
    open_weights: Mapped[bool | None]


class AiModelAlias(Base):
    """A site's own spelling of a model, kept as the console linked it (matched exactly)."""

    __tablename__ = "ai_model_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(200), unique=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("ai_models.id", ondelete="CASCADE"), index=True
    )


class BenchmarkSnapshot(Base):
    """One fetch of a leaderboard site. The same bytes are stored once per site (sha256)."""

    __tablename__ = "benchmark_snapshots"
    __table_args__ = (UniqueConstraint("site", "sha256", name="uq_benchmark_snapshots_site_sha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str] = mapped_column(String(40))
    release: Mapped[str] = mapped_column(String(40))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)


class BenchmarkScore(Base):
    """One model's value on one board of a snapshot. `model_id` stays empty until the model's
    name is matched (automatically, or in the console)."""

    __tablename__ = "benchmark_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_snapshots.id", ondelete="CASCADE"), index=True
    )
    site: Mapped[str] = mapped_column(String(40))
    board: Mapped[str] = mapped_column(String(60))
    model_raw: Mapped[str] = mapped_column(String(200))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("ai_models.id"), index=True)
    org: Mapped[str | None] = mapped_column(String(80))
    config: Mapped[str | None] = mapped_column(String(120))
    metric: Mapped[str] = mapped_column(String(60))
    value: Mapped[float] = mapped_column(Float)
    ci_low: Mapped[float | None] = mapped_column(Float)
    ci_high: Mapped[float | None] = mapped_column(Float)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
