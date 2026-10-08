"""Signal trends from metric snapshots: which items gained the most over a window."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from news_insight.content.models import Item
from news_insight.sources.enums import Track


@dataclass(frozen=True)
class Mover:
    item: Item
    current: int
    baseline: int
    delta: int


# Per item with at least two integer readings of the metric: the latest reading (current) and the
# latest one at or before the window start, or the first one when all fall inside (baseline).
# Computed in the database: the Python version loaded every snapshot with its item (bodies
# included) on each call, 3-10 s for the console dashboard's three metrics (2026-10-08).
MOVERS_SQL = """
WITH points AS (
    SELECT s.item_id, s.captured_at, (s.metrics ->> :metric)::bigint AS value
    FROM item_metric_snapshots s
    {track_join}
    WHERE s.captured_at <= :now
      AND jsonb_typeof(s.metrics -> :metric) = 'number'
      AND (s.metrics ->> :metric) ~ '^-?[0-9]+$'
), series AS (
    SELECT item_id,
           (array_agg(value ORDER BY captured_at DESC))[1] AS current,
           (array_agg(value ORDER BY captured_at DESC) FILTER (WHERE captured_at <= :cutoff))[1]
               AS before,
           (array_agg(value ORDER BY captured_at))[1] AS first
    FROM points
    GROUP BY item_id
    HAVING count(*) >= 2
)
SELECT item_id, current, coalesce(before, first) AS baseline
FROM series
ORDER BY current - coalesce(before, first) DESC, item_id
LIMIT :limit
"""


def metric_movers(
    session: Session,
    *,
    metric: str,
    window: timedelta,
    now: datetime,
    track: Track | None = None,
    limit: int = 20,
) -> list[Mover]:
    track_join = "JOIN items i ON i.id = s.item_id AND i.track = :track" if track else ""
    params: dict[str, object] = {
        "metric": metric,
        "now": now,
        "cutoff": now - window,
        "limit": limit,
    }
    if track is not None:
        params["track"] = track.value
    rows = session.execute(text(MOVERS_SQL.format(track_join=track_join)), params).all()
    items = {
        item.id: item
        for item in session.scalars(select(Item).where(Item.id.in_([row.item_id for row in rows])))
    }
    return [
        Mover(
            item=items[row.item_id],
            current=int(row.current),
            baseline=int(row.baseline),
            delta=int(row.current) - int(row.baseline),
        )
        for row in rows
        if row.item_id in items
    ]
