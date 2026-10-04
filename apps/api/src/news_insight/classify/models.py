"""Item labels (taxonomy axes) and canonical keywords derived from Korean cards."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from news_insight.classify.taxonomy import Axis
from news_insight.db import Base, str_enum

CURRENT = text("superseded_at IS NULL")


class LabelMethod(StrEnum):
    LLM = "llm"
    RULE = "rule"


class AliasOrigin(StrEnum):
    SEED = "seed"  # catalog/keyword_aliases.yaml
    AUTO = "auto"  # first sight of a new spelling


class ItemLabel(Base):
    """One taxonomy node assigned to an item.

    Append-only: a relabel marks the item's current rows superseded and adds new ones, so
    every label keeps the taxonomy revision, method and engine/model that produced it.
    """

    __tablename__ = "item_labels"
    __table_args__ = (
        Index(
            "uq_item_labels_current",
            "item_id",
            "axis",
            "node_key",
            unique=True,
            postgresql_where=CURRENT,
        ),
        Index("ix_item_labels_current_node", "axis", "node_key", postgresql_where=CURRENT),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    axis: Mapped[Axis] = mapped_column(str_enum(Axis))
    node_key: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float | None] = mapped_column(Float)
    method: Mapped[LabelMethod] = mapped_column(str_enum(LabelMethod))
    taxonomy_rev: Mapped[int]
    engine: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(80))
    labeled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Keyword(Base):
    """A canonical keyword; first_seen_at is the earliest item that mentioned it."""

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical: Mapped[str] = mapped_column(String(80), unique=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KeywordAlias(Base):
    """Matching key (see `keyword_key`) → canonical keyword."""

    __tablename__ = "keyword_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(80), unique=True)
    keyword_id: Mapped[int] = mapped_column(
        ForeignKey("keywords.id", ondelete="CASCADE"), index=True
    )
    origin: Mapped[AliasOrigin] = mapped_column(str_enum(AliasOrigin))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    keyword: Mapped[Keyword] = relationship()


class ItemKeyword(Base):
    """Canonical keywords of an item's current card (derived from item_cards.keywords)."""

    __tablename__ = "item_keywords"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    keyword_id: Mapped[int] = mapped_column(
        ForeignKey("keywords.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
