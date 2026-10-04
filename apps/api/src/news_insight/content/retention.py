"""Retention: drop `fulltext_ttl` bodies once their 30-day window has passed (D9) and thin out
old metric snapshots (DATA-1)."""

from datetime import datetime, timedelta

from sqlalchemy import text, update
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


DAILY_AFTER = timedelta(days=30)
WEEKLY_AFTER = timedelta(days=180)

_DOWNSAMPLE = text(
    """
    DELETE FROM item_metric_snapshots AS s
    USING (
        SELECT id,
               row_number() OVER (PARTITION BY item_id, bucket ORDER BY captured_at DESC) AS latest,
               row_number() OVER (PARTITION BY item_id ORDER BY captured_at) AS earliest
        FROM (
            SELECT id, item_id, captured_at,
                   CASE WHEN captured_at < :weekly
                        THEN date_trunc('week', captured_at AT TIME ZONE 'Asia/Seoul')
                        ELSE date_trunc('day', captured_at AT TIME ZONE 'Asia/Seoul')
                   END AS bucket
            FROM item_metric_snapshots
            WHERE item_id IN (
                SELECT item_id FROM item_metric_snapshots WHERE captured_at < :daily
            )
        ) AS b
    ) AS r
    WHERE s.id = r.id AND s.captured_at < :daily AND r.latest > 1 AND r.earliest > 1
    """
)


def downsample_snapshots(session: Session, now: datetime) -> int:
    """Metric snapshots older than 30 days keep one per item and KST day, older than 180 days one
    per item and KST week (checklist DATA-1). The kept row is the bucket's last, so a window that
    starts on a day (or week) boundary still finds the reading just before it; each item's first
    snapshot stays as the baseline for items first seen inside a window."""
    result = session.execute(
        _DOWNSAMPLE, {"daily": now - DAILY_AFTER, "weekly": now - WEEKLY_AFTER}
    )
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)
