from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class Relation(StrEnum):
    SEED = "seed"  # first item of a story
    EXACT = "exact"  # same URL (AMP/mobile unified) or same content hash
    NEAR = "near"  # near-duplicate report (MinHash >= near threshold)
    EVENT = "event"  # same event: similar title + shared entity keyword + close dates


class ItemSignature(Base):
    __tablename__ = "item_signatures"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    dedup_key: Mapped[str] = mapped_column(String(2048), index=True)
    signature: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ItemLsh(Base):
    __tablename__ = "item_lsh"
    __table_args__ = (Index("ix_item_lsh_band_hash", "band", "hash"),)

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    band: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    hash: Mapped[int] = mapped_column(BigInteger)


class Story(Base):
    """One issue: every report of the same event across sources, tracks and languages."""

    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(primary_key=True)
    representative_item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    title_ko: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    item_count: Mapped[int] = mapped_column(default=1)
    source_count: Mapped[int] = mapped_column(default=1)
    tracks: Mapped[list[str]] = mapped_column(JSONB, default=list)
    max_relevance: Mapped[int | None]


class StoryItem(Base):
    __tablename__ = "story_items"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    relation: Mapped[Relation] = mapped_column(str_enum(Relation))
    similarity: Mapped[float | None] = mapped_column(Float)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ItemRef(Base):
    """Identifiers that link tracks: arXiv id, DOI, GitHub repository."""

    __tablename__ = "item_refs"
    __table_args__ = (Index("ix_item_refs_kind_value", "kind", "value"),)

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    value: Mapped[str] = mapped_column(String(300), primary_key=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
