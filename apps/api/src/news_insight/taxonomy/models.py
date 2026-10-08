"""Classification schemes and nodes of any depth (plan 15).

A scheme is a kind of classification (technology, signal type, impact, scope, and whatever the
console adds); its nodes form a tree of any depth, branch by branch. Cards point at the most
specific nodes they belong to (`card_labels`); ancestors come from `TaxNode.path`. Node ids never
change, so renames and moves keep every count and time series.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class TaxScheme(Base):
    __tablename__ = "tax_schemes"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    structure: Mapped[str] = mapped_column(String(10), default="tree")  # tree | list
    min_labels: Mapped[int] = mapped_column(Integer, default=0)
    max_labels: Mapped[int] = mapped_column(Integer, default=3)  # LLM picks per card
    llm_depth: Mapped[int | None] = mapped_column(Integer)  # deepest level the LLM chooses
    level_names: Mapped[list[str]] = mapped_column(JSONB, default=list)
    uses: Mapped[list[str]] = mapped_column(JSONB, default=list)  # radar, filters, watch, ...
    sort: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaxNode(Base):
    __tablename__ = "tax_nodes"
    __table_args__ = (
        UniqueConstraint("scheme_id", "key", name="uq_tax_nodes_scheme_key"),
        Index("ix_tax_nodes_path", "path", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scheme_id: Mapped[int] = mapped_column(ForeignKey("tax_schemes.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tax_nodes.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(120))
    definition: Mapped[str | None] = mapped_column(Text)
    include_text: Mapped[str | None] = mapped_column(Text)
    exclude_text: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("tax_nodes.id"))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)  # ancestors + self
    depth: Mapped[int] = mapped_column(Integer, default=1)
    edited_in_console: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TaxRelation(Base):
    """`implies`: a card on `from_node` also gets `to_node` (derived labels across schemes)."""

    __tablename__ = "tax_relations"
    __table_args__ = (
        UniqueConstraint("from_node_id", "to_node_id", "kind", name="uq_tax_relations_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("tax_nodes.id", ondelete="CASCADE"))
    to_node_id: Mapped[int] = mapped_column(
        ForeignKey("tax_nodes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="implies")


class TaxRevision(Base):
    __tablename__ = "tax_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    author: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="applied")  # draft|applied|rolled_back
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class CardLabel(Base):
    """A card on a node. `legacy` rows mirror the old item_cards columns (trigger, plan 15-1)."""

    __tablename__ = "card_labels"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[int] = mapped_column(
        ForeignKey("tax_nodes.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    scheme_id: Mapped[int] = mapped_column(ForeignKey("tax_schemes.id"), index=True)
    source: Mapped[str] = mapped_column(String(20))  # legacy | llm | rule | derived | human
    confidence: Mapped[float | None] = mapped_column(Float)
    revision_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
