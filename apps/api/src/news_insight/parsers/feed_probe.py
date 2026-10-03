"""V3 parser reliability probe for RSS/Atom feeds."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import feedparser

from news_insight.sources.ladder import CheckResult

MIN_PROBE_ITEMS = 3


@dataclass(frozen=True)
class ProbedItem:
    stable_id: str
    url: str
    title: str
    published_at: datetime


def extract_items(content: bytes) -> list[ProbedItem]:
    """Return entries that carry every field V3 requires: id, url, title, published date."""
    parsed = feedparser.parse(content)
    items: list[ProbedItem] = []
    for entry in parsed.entries:
        url = str(entry.get("link") or "").strip()
        stable_id = str(entry.get("id") or url).strip()
        title = str(entry.get("title") or "").strip()
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if not (stable_id and url and title and published):
            continue
        year, month, day, hour, minute, second = (int(part) for part in published[:6])
        items.append(
            ProbedItem(
                stable_id=stable_id,
                url=url,
                title=title,
                published_at=datetime(year, month, day, hour, minute, second, tzinfo=UTC),
            )
        )
    return items


def probe_feed(
    content: bytes,
    *,
    now: datetime,
    min_items: int = MIN_PROBE_ITEMS,
    max_age_days: int = 30,
) -> CheckResult:
    parsed = feedparser.parse(content)
    if not parsed.entries:
        detail = str(parsed.get("bozo_exception") or "no entries")
        return CheckResult.from_reasons(
            [f"feed could not be parsed: {detail}"], {"entries": 0, "complete": 0, "recent": 0}
        )
    items = extract_items(content)
    cutoff = now - timedelta(days=max_age_days)
    recent = [item for item in items if item.published_at >= cutoff]
    reasons: list[str] = []
    if len(recent) < min_items:
        reasons.append(f"only {len(recent)} recent complete items (need {min_items})")
    return CheckResult.from_reasons(
        reasons, {"entries": len(parsed.entries), "complete": len(items), "recent": len(recent)}
    )
