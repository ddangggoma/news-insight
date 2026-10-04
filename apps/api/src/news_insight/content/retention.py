"""Retention: drop `fulltext_ttl` bodies once their 30-day window has passed (D9)."""

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from news_insight.content.models import Item


def purge_expired_bodies(session: Session, now: datetime) -> int:
    """One UPDATE on the partial `body_expires_at` index (checklist DATA-2)."""
    result = session.execute(
        update(Item)
        .where(Item.body_expires_at.is_not(None), Item.body_expires_at <= now)
        .values(body=None, body_expires_at=None)
        .execution_options(synchronize_session="fetch")
    )
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)
