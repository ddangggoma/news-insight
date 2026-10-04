from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class CardStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"  # gave up after MAX_ATTEMPTS; the item still shows its original title


class ItemCard(Base):
    """Korean card for one collected item (title, up to 3 summary lines, keywords)."""

    __tablename__ = "item_cards"
    __table_args__ = (Index("ix_item_cards_generated_at", "generated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), unique=True)
    status: Mapped[CardStatus] = mapped_column(str_enum(CardStatus))
    title_ko: Mapped[str | None] = mapped_column(Text)
    summary_ko: Mapped[list[str]] = mapped_column(JSONB, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    engine: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(80))
    input_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CardRun(Base):
    """One host-side card generation run (launchd every 10 min) for the console."""

    __tablename__ = "card_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    batches: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    quota: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(Text)
