from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class EnrichStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"  # OpenAlex does not know the DOI (yet): asked again after 7 days
    ERROR = "error"  # the answer could not be read: asked again the next day


class ResearchMeta(Base):
    """OpenAlex metadata of one paper (plan 19 §2.1), 1:1 with items.

    `institutions` is [{name, type, country, ror, company_key}] in author order;
    `company_keys` are the registry companies among the institutions of type "company"
    (matched through company_aliases); the other names are counted as organisations
    (`research_daily_stats.org_name`)."""

    __tablename__ = "research_meta"
    __table_args__ = (
        Index("ix_research_meta_status_enriched_at", "status", "enriched_at"),
        Index("ix_research_meta_company_keys", "company_keys", postgresql_using="gin"),
        Index("ix_research_meta_doi", "doi"),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    # the paper's DOI (arXiv: 10.48550/arxiv.*); none for a work looked up by OpenAlex id that
    # has no DOI
    doi: Mapped[str | None] = mapped_column(String(300))
    openalex_id: Mapped[str | None] = mapped_column(String(40))
    venue: Mapped[str | None] = mapped_column(String(300))
    oa_field: Mapped[str | None] = mapped_column(String(120))
    oa_subfield: Mapped[str | None] = mapped_column(String(120))
    oa_topic: Mapped[str | None] = mapped_column(String(300))
    institutions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    countries: Mapped[list[str]] = mapped_column(
        ARRAY(String(2)), default=list, server_default=text("'{}'")
    )
    has_company: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    company_keys: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), default=list, server_default=text("'{}'")
    )
    cited_by: Mapped[int | None]
    fwci: Mapped[float | None] = mapped_column(Float)
    counts_by_year: Mapped[list[dict[str, int]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[EnrichStatus] = mapped_column(str_enum(EnrichStatus))
    error: Mapped[str | None] = mapped_column(Text)
    enriched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchDailyStat(Base):
    """Research documents per KST day (plan 19 §2.3), one breakdown per row.

    `dim` names the breakdown and which key column is filled; the other key columns are '':
    total (field only), theme (field = the theme's own field), company (company_key),
    org (org_name + org_type: institutions not linked to a registry company), country.
    `n` counts documents, `n_company` those with a company-type institution. Rebuilt per day
    by insights.stats (delete + insert), so a day's rows are always one consistent pass."""

    __tablename__ = "research_daily_stats"
    __table_args__ = (
        Index("ix_research_daily_stats_dim_day", "dim", "day"),
        # an institution's rows (org detail): the org dimension is most of the table
        Index("ix_research_daily_stats_dim_org_day", "dim", "org_name", "day"),
    )

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    dim: Mapped[str] = mapped_column(String(10), primary_key=True)
    field: Mapped[str] = mapped_column(String(40), primary_key=True)
    theme: Mapped[str] = mapped_column(String(80), primary_key=True, default="")
    company_key: Mapped[str] = mapped_column(String(80), primary_key=True, default="")
    org_name: Mapped[str] = mapped_column(String(200), primary_key=True, default="")
    country: Mapped[str] = mapped_column(String(2), primary_key=True, default="")
    org_type: Mapped[str] = mapped_column(String(20), default="")
    n: Mapped[int]
    n_company: Mapped[int] = mapped_column(default=0)


class ResearchSignal(Base):
    """Per research document of the last ~100 days (plan 19 §1 주목 문헌): what the documents
    list filters and ranks by, rebuilt daily after the counts (insights/signals.py) up to the
    same as_of. Listings of one paper (arXiv and Hugging Face, a DOI and its arXiv id) share a
    `canon_key`; the group's lead (`lead`, `lead_id` = item_id) carries the group's signals and
    the union of its companies and institutions, the other rows point to it.

    score = 10 × mentions + upvotes + 5 × ln(1 + cited_growth); mentions = news and community
    items citing the paper's own DOI or arXiv id up to as_of (repeats left out); upvotes = the
    Hugging Face daily papers count; cited_growth = OpenAlex citations of as_of's year minus
    the year before (never below 0)."""

    __tablename__ = "research_signals"
    __table_args__ = (
        Index("ix_research_signals_lead_day", "day", postgresql_where=text("lead")),
        Index("ix_research_signals_company_keys", "company_keys", postgresql_using="gin"),
        Index("ix_research_signals_orgs", "orgs", postgresql_using="gin"),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    day: Mapped[date] = mapped_column(Date)  # KST
    field: Mapped[str] = mapped_column(String(40))  # card field, else "other" (as the counts)
    company_keys: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), default=list, server_default=text("'{}'")
    )
    orgs: Mapped[list[str]] = mapped_column(
        ARRAY(String(200)), default=list, server_default=text("'{}'")
    )
    canon_key: Mapped[str | None] = mapped_column(String(320))
    lead: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    lead_id: Mapped[int]
    mentions: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    upvotes: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    cited_growth: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    score: Mapped[float] = mapped_column(Float, default=0.0, server_default=text("0"))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
