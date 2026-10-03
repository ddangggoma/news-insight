"""Retention: drop `fulltext_ttl` bodies once their 30-day window has passed (D9)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item


def purge_expired_bodies(session: Session, now: datetime) -> int:
    expired = list(
        session.scalars(
            select(Item).where(Item.body_expires_at.is_not(None), Item.body_expires_at <= now)
        )
    )
    for item in expired:
        item.body = None
        item.body_expires_at = None
    session.flush()
    return len(expired)
