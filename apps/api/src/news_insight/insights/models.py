from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


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


class InsightKind(StrEnum):
    RESEARCH = "research"
    PATENT = "patent"


class InsightStatus(StrEnum):
    PUBLISHED = "published"
    FAILED = "failed"  # the writer or its checks failed: the next digest run tries again


class DomainInsightRecord(Base):
    """One day's Opus insight of the 연구 or 특허 menu (plan 19 §3). `payload` holds the
    validated output: overview [{text, doc_ids}], fields [{field, text, doc_ids}], companies
    [{company_key, text, doc_ids}], watch, and the as_of its input ended on. Published rows are
    immutable; a failed row is overwritten by the next attempt."""

    __tablename__ = "domain_insights"
    __table_args__ = (
        UniqueConstraint("insight_date", "kind", name="uq_domain_insights_date_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    insight_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[InsightKind] = mapped_column(str_enum(InsightKind))
    status: Mapped[InsightStatus] = mapped_column(str_enum(InsightStatus))
    model: Mapped[str] = mapped_column(String(80))
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4, asdecimal=False))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
