from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class Dossier(Base):
    """A topic the team follows (plan 16 #4): which cards belong to it, defined by taxonomy
    nodes (with their subtrees), registered companies, keywords and a sentence matched by
    meaning, any of which brings a card in; excluded words keep it out. Shared by every user."""

    __tablename__ = "dossiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    nodes: Mapped[list[str]] = mapped_column(JSONB, default=list)  # scheme:key
    companies: Mapped[list[str]] = mapped_column(JSONB, default=list)  # registry keys
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    exclude: Mapped[list[str]] = mapped_column(JSONB, default=list)
    statement: Mapped[str | None] = mapped_column(Text)
    statement_embedding: Mapped[Any] = mapped_column(Vector(1024), nullable=True)
    min_similarity: Mapped[float] = mapped_column(Float, default=0.6)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DossierHypothesis(Base):
    """A claim about the topic the team tests against the cards."""

    __tablename__ = "dossier_hypotheses"

    id: Mapped[int] = mapped_column(primary_key=True)
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    embedding: Mapped[Any] = mapped_column(Vector(1024), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DossierEvidence(Base):
    """A card attached to a hypothesis as support, counter-evidence or context."""

    __tablename__ = "dossier_evidence"
    __table_args__ = (
        UniqueConstraint("hypothesis_id", "item_id", name="uq_dossier_evidence_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hypothesis_id: Mapped[int] = mapped_column(
        ForeignKey("dossier_hypotheses.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    stance: Mapped[str] = mapped_column(String(10))  # support | oppose | context
    note: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
