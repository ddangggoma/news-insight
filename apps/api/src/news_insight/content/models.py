from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, false, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from news_insight.db import Base, str_enum
from news_insight.sources.enums import Track


class Item(Base):
    """Latest stored state of one source item (seen-ledger key: source_id + stable_id)."""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("source_id", "stable_id", name="uq_items_source_stable"),
        Index("ix_items_title_lower", text("lower(title)")),  # same-headline story lookup
        Index(
            "ix_items_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        # time windows drive the feed, radar, briefing freeze and card queue (checklist PERF-1)
        Index("ix_items_first_seen_at", "first_seen_at"),
        Index("ix_items_source_first_seen", "source_id", "first_seen_at"),
        Index(
            "ix_items_body_expires_at",
            "body_expires_at",
            postgresql_where=text("body_expires_at IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    track: Mapped[Track] = mapped_column(str_enum(Track))
    stable_id: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str] = mapped_column(String(2048), index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    body_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    canary: Mapped[bool] = mapped_column(default=False, server_default=false())
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    revisions: Mapped[list["ItemRevision"]] = relationship(
        back_populates="item", order_by="ItemRevision.revision"
    )


class ItemRevision(Base):
    """Append-only provenance: every real content change and the run that observed it."""

    __tablename__ = "item_revisions"
    __table_args__ = (
        UniqueConstraint("item_id", "revision", name="uq_item_revisions_item_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    fetch_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("fetch_runs.id", ondelete="SET NULL")
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    item: Mapped[Item] = relationship(back_populates="revisions")


class ItemMetricSnapshot(Base):
    """Engagement signals over time (stars, likes, points); deltas feed trend detection."""

    __tablename__ = "item_metric_snapshots"
    __table_args__ = (
        Index("ix_item_metric_snapshots_item_captured", "item_id", "captured_at"),
        Index("ix_item_metric_snapshots_captured_at", "captured_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
