from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class PatentSource(StrEnum):
    OPS = "ops"  # EPO OPS bibliographic search (applicants; CPC of the source's query)
    EPS = "eps"  # EPO publication server pilot (IPC from the bibliography, no applicants)
    NEWS = "news"  # a card the engines marked as intellectual property (signal_type "ip")


class PatentMeta(Base):
    """Patent metadata of one item (plan 19 §2.2), 1:1 with items.

    `field` is the technology field of the first classification the CPC/IPC map knows
    (catalog/cpc_fields.yaml), else the card's field, else "other"; `fields` every field the
    classifications map to (main one first). Codes are stored as "G06N 3/08" (or the bare
    subclass "G06N" when only that is known, as for OPS queries)."""

    __tablename__ = "patent_meta"
    __table_args__ = (
        Index("ix_patent_meta_company_keys", "company_keys", postgresql_using="gin"),
        Index("ix_patent_meta_field", "field"),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    publication_number: Mapped[str | None] = mapped_column(String(40))  # "EP4815726", no kind
    kind: Mapped[str | None] = mapped_column(String(4))  # "A1", "B2"
    office: Mapped[str | None] = mapped_column(String(4))  # publishing office: EP, US, CN, WO
    priority_date: Mapped[date | None] = mapped_column(Date)
    cpc: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list, server_default="{}")
    ipc: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list, server_default="{}")
    applicants: Mapped[list[str]] = mapped_column(
        ARRAY(String(300)), default=list, server_default="{}"
    )
    company_keys: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), default=list, server_default="{}"
    )
    field: Mapped[str] = mapped_column(String(40))
    fields: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list, server_default="{}")
    source: Mapped[PatentSource] = mapped_column(str_enum(PatentSource))
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PatentDailyStat(Base):
    """Patent documents per KST day (plan 19 §2.3), one breakdown per row.

    `dim` is total (field and source only), company (company_key) or office; the other key
    column is ''. `source` (ops | eps | news) splits office publications from patent news so
    the screen can show both and its data-coverage note. Rebuilt per day by insights.stats."""

    __tablename__ = "patent_daily_stats"
    __table_args__ = (Index("ix_patent_daily_stats_dim_day", "dim", "day"),)

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    dim: Mapped[str] = mapped_column(String(10), primary_key=True)
    field: Mapped[str] = mapped_column(String(40), primary_key=True)
    source: Mapped[str] = mapped_column(String(8), primary_key=True)
    company_key: Mapped[str] = mapped_column(String(80), primary_key=True, default="")
    office: Mapped[str] = mapped_column(String(4), primary_key=True, default="")
    n: Mapped[int]
