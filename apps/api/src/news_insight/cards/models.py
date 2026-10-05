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
    __table_args__ = (
        Index("ix_item_cards_generated_at", "generated_at"),
        Index("ix_item_cards_keywords", "keywords", postgresql_using="gin"),
        Index("ix_item_cards_themes", "themes", postgresql_using="gin"),
        Index("ix_item_cards_technology_keys", "technology_keys", postgresql_using="gin"),
        Index("ix_item_cards_company_keys", "company_keys", postgresql_using="gin"),
        Index(
            "ix_item_cards_title_ko_trgm",
            "title_ko",
            postgresql_using="gin",
            postgresql_ops={"title_ko": "gin_trgm_ops"},
        ),
    )

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
    # classification (P4) against taxonomy_revision
    field: Mapped[str | None] = mapped_column(String(40), index=True)
    themes: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    businesses: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    signal_type: Mapped[str | None] = mapped_column(String(20), index=True)
    impact: Mapped[str | None] = mapped_column(String(20))
    scope: Mapped[str | None] = mapped_column(String(20), index=True)
    relevance: Mapped[int | None]
    taxonomy_revision: Mapped[str | None] = mapped_column(String(20))
    # classification-only retries against the current revision (checklist CLS-2)
    classify_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    # canonical keyword keys (technology registry, checklist KW-1); set on every write
    technology_keys: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # phrases the theme list does not cover (checklist CLS-1)
    topic_candidates: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # companies and organisations the item is about, as the engine wrote them (plan 12)
    companies: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # registered company keys matched from `companies` and `keywords`; set by a trigger
    company_keys: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")


class CardRun(Base):
    """One host-side card generation run (launchd every 10 min) for the console."""

    __tablename__ = "card_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    classified: Mapped[int] = mapped_column(default=0, server_default="0")
    batches: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    quota: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(Text)
