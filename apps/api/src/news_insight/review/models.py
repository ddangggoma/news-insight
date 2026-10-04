from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class Verdict(StrEnum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    UNSURE = "unsure"


class RelevanceReview(Base):
    """Operator's DX-relevance label for one item (latest verdict wins). Also the P4 eval set."""

    __tablename__ = "relevance_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), unique=True)
    verdict: Mapped[Verdict] = mapped_column(str_enum(Verdict))
    note: Mapped[str | None] = mapped_column(Text)
    sample_seed: Mapped[str | None] = mapped_column(String(40))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
