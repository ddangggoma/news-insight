"""Platform-normalised engagement: a post's raw counts mean different things on HN, Bluesky and
GitHub, so each is turned into a per-hour velocity and then a z-score within its own platform
(falling back to the pooled community·oss distribution while a platform has too few samples)."""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.sources.enums import Track
from news_insight.sources.models import Source

MIN_SAMPLE = 30
_MIN_HOURS = 2.0

_SCORE_ANSWERS = ("score", "answers")
# Source operator -> metric keys summed into one engagement number. Operators are the strings in
# apps/api/catalog/sources.yaml; V2EX has one operator per node, hence the explicit list.
PLATFORM_METRICS: dict[str, tuple[str, ...]] = {
    "Algolia (HN Search)": ("points", "comments"),
    "Y Combinator": ("points", "comments"),
    "Mastodon gGmbH": ("favourites", "reblogs", "replies"),
    "Fosstodon": ("favourites", "reblogs", "replies"),
    "mstdn.jp": ("favourites", "reblogs", "replies"),
    "Bluesky Social PBC": ("likes", "reposts", "replies"),
    "DEV Community": ("reactions", "comments"),
    "Stack Exchange Inc.": _SCORE_ANSWERS,
    **{
        f"V2EX{node}": _SCORE_ANSWERS
        for node in (
            "",
            " Android",
            " Apple",
            " Linux",
            " NAS",
            " OpenAI",
            " Python",
            " Windows",
            " iPhone",
            " macOS",
            " 云计算",
            " 分享创造",
            " 汽车",
            " 硬件",
            " 程序员",
        )
    },
    "GitHub": ("trending_stars_daily",),
    "Hugging Face": ("trending", "likes"),
    "Google LLC (YouTube Data API)": ("views",),
    "Hugging Face Daily Papers": ("upvotes", "comments"),
}
# Operators whose first listed key is a standalone signal: later keys are only a fallback.
_FIRST_KEY_ONLY = frozenset({"Hugging Face"})


@dataclass(frozen=True)
class PlatformStats:
    mean: float
    std: float
    n: int


def engagement(operator: str, metrics: dict[str, int]) -> int | None:
    keys = PLATFORM_METRICS.get(operator)
    if keys is None:
        return None
    present = [key for key in keys if isinstance(metrics.get(key), int)]
    if not present:
        return None
    if operator in _FIRST_KEY_ONLY:
        present = present[:1]
    # Stack Exchange / V2EX scores can be negative; engagement is never below zero.
    return max(sum(metrics[key] for key in present), 0)


def velocity(value: int, published: datetime | None, first_seen: datetime, at: datetime) -> float:
    hours = (at - (published or first_seen)).total_seconds() / 3600
    return math.log1p(max(value, 0) / max(hours, _MIN_HOURS))


def zscore(v: float, stats: PlatformStats | None, fallback: PlatformStats) -> float:
    chosen = stats if stats is not None and stats.n >= MIN_SAMPLE else fallback
    if chosen.std == 0:
        return 0.0
    return (v - chosen.mean) / chosen.std


def _stats(values: list[float]) -> PlatformStats:
    n = len(values)
    if n == 0:
        return PlatformStats(mean=0.0, std=0.0, n=0)
    mean = sum(values) / n
    return PlatformStats(mean=mean, std=math.sqrt(sum((v - mean) ** 2 for v in values) / n), n=n)


def platform_stats(
    session: Session, *, at: datetime, days: int = 7
) -> tuple[dict[str, PlatformStats], PlatformStats]:
    """Velocity distribution per operator and pooled over community·oss items first seen in the
    last `days` days, each item at its latest metrics snapshot taken by `at`. Papers of Hugging
    Face Daily Papers (a research track) have a distribution of their own but stay out of the
    pool."""
    latest = (
        select(ItemMetricSnapshot.item_id, ItemMetricSnapshot.metrics)
        .where(ItemMetricSnapshot.captured_at <= at)
        .distinct(ItemMetricSnapshot.item_id)
        .order_by(ItemMetricSnapshot.item_id, ItemMetricSnapshot.captured_at.desc())
        .subquery()
    )
    rows = session.execute(
        select(Source.operator, Item.track, Item.published_at, Item.first_seen_at, latest.c.metrics)
        .join(Item, Item.source_id == Source.id)
        .join(latest, latest.c.item_id == Item.id)
        .where(
            Item.track.in_((Track.COMMUNITY, Track.OSS, Track.RESEARCH_IP)),
            Item.first_seen_at >= at - timedelta(days=days),
            Item.first_seen_at <= at,
        )
    ).all()
    by_operator: dict[str, list[float]] = defaultdict(list)
    pooled: list[float] = []
    for operator, track, published, first_seen, metrics in rows:
        value = engagement(operator, metrics)
        if value is not None:
            v = velocity(value, published, first_seen, at)
            by_operator[operator].append(v)
            if track is not Track.RESEARCH_IP:
                pooled.append(v)
    return {op: _stats(values) for op, values in by_operator.items()}, _stats(pooled)
