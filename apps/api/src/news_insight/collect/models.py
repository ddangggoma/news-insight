from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class FetchOutcome(StrEnum):
    SUCCESS = "success"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"  # will be retried with backoff
    DEAD_LETTERED = "dead_lettered"
    SKIPPED = "skipped"  # not attempted: local rate budget or not collectable


class SourceRuntime(Base):
    """Mutable scheduling state, kept apart from the governed source registry."""

    __tablename__ = "source_runtimes"

    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True, autoincrement=False
    )
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    interval_seconds: Mapped[int]
    consecutive_failures: Mapped[int] = mapped_column(default=0, server_default="0")
    consecutive_idle: Mapped[int] = mapped_column(default=0, server_default="0")
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(200))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FetchRun(Base):
    """One collection attempt; the V4 canary aggregates these."""

    __tablename__ = "fetch_runs"
    __table_args__ = (Index("ix_fetch_runs_source_started", "source_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[FetchOutcome] = mapped_column(str_enum(FetchOutcome))
    attempt: Mapped[int] = mapped_column(default=1, server_default="1")
    canary: Mapped[bool] = mapped_column(default=False, server_default=false())
    http_status: Mapped[int | None]
    elapsed_ms: Mapped[int | None]
    items_seen: Mapped[int] = mapped_column(default=0, server_default="0")
    items_new: Mapped[int] = mapped_column(default=0, server_default="0")
    items_updated: Mapped[int] = mapped_column(default=0, server_default="0")
    items_unchanged: Mapped[int] = mapped_column(default=0, server_default="0")
    items_incomplete: Mapped[int] = mapped_column(default=0, server_default="0")
    duplicate_urls: Mapped[int] = mapped_column(default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class DeadLetter(Base):
    __tablename__ = "dead_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    fetch_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("fetch_runs.id", ondelete="SET NULL")
    )
    error_code: Mapped[str] = mapped_column(String(80))
    error_message: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(20))
