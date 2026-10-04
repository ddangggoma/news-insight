from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum
from news_insight.technologies.catalog import TechKind, TechStatus


class Technology(Base):
    """Third level of the technology axis (plan 09 §3-3): a canonical keyword key."""

    __tablename__ = "technologies"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    theme_key: Mapped[str | None] = mapped_column(String(80), index=True)
    kind: Mapped[TechKind] = mapped_column(str_enum(TechKind), default=TechKind.TECHNOLOGY)
    status: Mapped[TechStatus] = mapped_column(str_enum(TechStatus), default=TechStatus.ACTIVE)
    edited_in_console: Mapped[bool] = mapped_column(default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TechnologyAlias(Base):
    __tablename__ = "technology_aliases"

    alias: Mapped[str] = mapped_column(String(80), primary_key=True)
    technology_key: Mapped[str] = mapped_column(
        ForeignKey("technologies.key", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )


class KeywordLabel(Base):
    """Most common spelling per keyword key, for display (refreshed nightly)."""

    __tablename__ = "keyword_labels"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    cards: Mapped[int] = mapped_column(Integer, default=0)
