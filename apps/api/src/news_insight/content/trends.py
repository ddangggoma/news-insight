"""Signal trends from metric snapshots: which items gained the most over a window."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.sources.enums import Track


@dataclass(frozen=True)
class Mover:
    item: Item
    current: int
    baseline: int
    delta: int


def metric_movers(
    session: Session,
    *,
    metric: str,
    window: timedelta,
    now: datetime,
    track: Track | None = None,
    limit: int = 20,
) -> list[Mover]:
    statement = (
        select(ItemMetricSnapshot, Item)
        .join(Item, Item.id == ItemMetricSnapshot.item_id)
        .where(ItemMetricSnapshot.captured_at <= now)
        .order_by(ItemMetricSnapshot.item_id, ItemMetricSnapshot.captured_at)
    )
    if track is not None:
        statement = statement.where(Item.track == track)
    series: dict[int, tuple[Item, list[tuple[datetime, int]]]] = {}
    for snapshot, item in session.execute(statement).tuples():
        value = snapshot.metrics.get(metric)
        if isinstance(value, int) and not isinstance(value, bool):
            series.setdefault(item.id, (item, []))[1].append((snapshot.captured_at, value))
    cutoff = now - window
    movers: list[Mover] = []
    for item, points in series.values():
        if len(points) < 2:
            continue
        before = [value for captured, value in points if captured <= cutoff]
        baseline = before[-1] if before else points[0][1]
        current = points[-1][1]
        movers.append(
            Mover(item=item, current=current, baseline=baseline, delta=current - baseline)
        )
    movers.sort(key=lambda mover: mover.delta, reverse=True)
    return movers[:limit]
