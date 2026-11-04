from datetime import date, datetime

from sqlalchemy import Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class StatsDay(Base):
    """One row per KST day whose research and patent counts were built (plan 19 §2.3): the
    reader's as_of is the last of them, the first bounds the history the trend flags may use.
    `research_enriched` counts the day's research documents with OpenAlex metadata, so the
    country, company and organisation trends can tell coverage growth from a real change."""

    __tablename__ = "stats_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    research_docs: Mapped[int] = mapped_column(default=0)
    research_enriched: Mapped[int] = mapped_column(default=0)
    patent_docs: Mapped[int] = mapped_column(default=0)
