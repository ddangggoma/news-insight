from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from news_insight.db import Base
from news_insight.sources.enums import (
    AccessMethod,
    PollClass,
    Region,
    SourceStatus,
    StorageRight,
    Track,
    ValidationOutcome,
    ValidationStage,
)


def _enum(enum_cls: type[StrEnum]) -> SAEnum:
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_status_stage", "status", "validation_stage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    track: Mapped[Track] = mapped_column(_enum(Track), index=True)
    category: Mapped[str] = mapped_column(String(40))
    access_method: Mapped[AccessMethod] = mapped_column(_enum(AccessMethod))
    endpoint_url: Mapped[str] = mapped_column(String(2048))
    official_domain: Mapped[str] = mapped_column(String(253))
    operator: Mapped[str] = mapped_column(String(200))
    region: Mapped[Region] = mapped_column(_enum(Region))
    language: Mapped[str] = mapped_column(String(16))
    poll_class: Mapped[PollClass] = mapped_column(_enum(PollClass))
    dx_relevance: Mapped[str] = mapped_column(Text)
    terms_url: Mapped[str | None] = mapped_column(String(2048))
    storage_right: Mapped[StorageRight | None] = mapped_column(_enum(StorageRight))
    validation_stage: Mapped[ValidationStage] = mapped_column(
        _enum(ValidationStage),
        default=ValidationStage.UNVERIFIED,
        server_default=ValidationStage.UNVERIFIED.value,
    )
    status: Mapped[SourceStatus] = mapped_column(
        _enum(SourceStatus),
        default=SourceStatus.CANDIDATE,
        server_default=SourceStatus.CANDIDATE.value,
    )
    paused_reason: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    validation_events: Mapped[list["SourceValidationEvent"]] = relationship(
        back_populates="source", order_by="SourceValidationEvent.id"
    )


class SourceValidationEvent(Base):
    """Append-only audit trail of every ladder check and reset."""

    __tablename__ = "source_validation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    stage: Mapped[ValidationStage] = mapped_column(_enum(ValidationStage))
    outcome: Mapped[ValidationOutcome] = mapped_column(_enum(ValidationOutcome))
    reasons: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[Source] = relationship(back_populates="validation_events")
