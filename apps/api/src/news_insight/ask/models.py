from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class CardEmbedding(Base):
    """bge-m3 embedding of a card's Korean title and summary, for questions over the corpus
    (plan 16 #1). No ANN index: an exact scan of ~100k vectors answers in seconds."""

    __tablename__ = "card_embeddings"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(100))
    embedding: Mapped[Any] = mapped_column(Vector(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
