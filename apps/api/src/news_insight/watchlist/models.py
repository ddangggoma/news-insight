from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class WatchItem(Base):
    """Something the reader follows (plan 13 A5): a company, a theme or a technology keyword."""

    __tablename__ = "watch_items"
    __table_args__ = (UniqueConstraint("kind", "key", name="uq_watch_items_kind_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # company | theme | keyword
    key: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
