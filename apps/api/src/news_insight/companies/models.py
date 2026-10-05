from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.companies.catalog import CompanyKind, CompanyRegion, CompanyStatus, Relation
from news_insight.db import Base, str_enum


class Company(Base):
    """A company or organisation the cards report on (plan 12)."""

    __tablename__ = "companies"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    name_ko: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[CompanyKind] = mapped_column(str_enum(CompanyKind), default=CompanyKind.COMPANY)
    region: Mapped[CompanyRegion] = mapped_column(
        str_enum(CompanyRegion), default=CompanyRegion.OTHER
    )
    relation: Mapped[Relation] = mapped_column(str_enum(Relation), default=Relation.PEER)
    themes: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    domains: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    status: Mapped[CompanyStatus] = mapped_column(
        str_enum(CompanyStatus), default=CompanyStatus.ACTIVE
    )
    edited_in_console: Mapped[bool] = mapped_column(default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompanyAlias(Base):
    """Normalised spelling → company (key, names and aliases all live here)."""

    __tablename__ = "company_aliases"

    alias: Mapped[str] = mapped_column(String(80), primary_key=True)
    company_key: Mapped[str] = mapped_column(
        ForeignKey("companies.key", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
