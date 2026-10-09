from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class Deal(Base):
    """An investment, acquisition, partnership or listing a card reports (plan 16 #8),
    extracted by the local Qwen; the card is its evidence."""

    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    actor: Mapped[str] = mapped_column(String(160))
    actor_key: Mapped[str | None] = mapped_column(String(80), index=True)  # company registry
    counterparty: Mapped[str | None] = mapped_column(String(160))
    counterparty_key: Mapped[str | None] = mapped_column(String(80), index=True)
    amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    amount_usd: Mapped[float | None] = mapped_column(Float)  # rough, fixed rates
    stage: Mapped[str | None] = mapped_column(String(40))
    announced_on: Mapped[date | None] = mapped_column(Date, index=True)
    summary: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(80))
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DealScan(Base):
    """A card already read for deals, whether or not it had any (so it is read once)."""

    __tablename__ = "deal_scans"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    found: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(80))
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
