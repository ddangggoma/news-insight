"""Repair stored article dates with the rules of content/dates.py (`news-insight items redate`).

Three passes over the items first seen in a window:

1. feeds: fetch the source's feed again and parse it with the source's zone. An item still in
   the feed takes the earlier of its stored and its fresh date. When most of those items moved
   by the same offset (a feed that writes zone-less local time), every other item of the
   source in the window moves by it too: the stored dates came from the same wrong reading.
2. every item: a date later than when we saw it is corrected or dropped (`plausible`); an
   item without a date takes the dateline in its text.
3. verification (optional): a few changed items per source, their article page's meta/JSON-LD
   publication date compared with the stored and the repaired date.
"""

import random
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from news_insight.collect.context import collect_context
from news_insight.collect.contracts import RawItem
from news_insight.collect.page_meta import extract_meta
from news_insight.content.dates import earliest, plausible, source_timezone, stated_date
from news_insight.content.models import Item
from news_insight.content.normalize import stable_key
from news_insight.net.mime import HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod
from news_insight.sources.models import Source

# items of a feed that must agree on one offset before it is applied to the rest
MIN_MATCHED = 3
AGREEMENT = 0.8
# a verified date within this of the page's own date counts as right
TOLERANCE = timedelta(minutes=10)

FeedReader = Callable[[Source, datetime], list[RawItem]]
PageReader = Callable[[str, tzinfo], datetime | None]


@dataclass
class SourceRepair:
    key: str
    name: str
    items: int = 0
    changed: int = 0
    matched: int = 0  # items still in the feed
    shift: timedelta | None = None  # offset applied to the rest of the window
    dropped: int = 0  # dates that could not be right
    from_text: int = 0  # dates taken from a dateline
    checked: int = 0
    right_before: int = 0
    right_after: int = 0
    error: str | None = None


@dataclass
class RedatePlan:
    since: datetime
    sources: list[SourceRepair] = field(default_factory=list)
    changes: dict[int, datetime | None] = field(default_factory=dict)  # item id → new date

    @property
    def changed(self) -> int:
        return len(self.changes)


def read_feed(fetcher: SafeFetcher) -> FeedReader:
    from news_insight.collect.registry import collector_for

    def read(source: Source, now: datetime) -> list[RawItem]:
        context = collect_context(source, now=now)
        return collector_for(AccessMethod.FEED, fetcher).collect(context).items

    return read


def read_page(fetcher: SafeFetcher) -> PageReader:
    def read(url: str, tz: tzinfo) -> datetime | None:
        response = fetcher.fetch(url, allowed_mime=HTML_MIME)
        if response.status_code != 200:
            return None
        html = response.content.decode("utf-8", errors="replace")
        return extract_meta(html, assume_tz=tz).published_at

    return read


def _modal_shift(deltas: list[timedelta]) -> timedelta | None:
    rounded = Counter(round(delta.total_seconds() / 60) for delta in deltas)
    if len(deltas) < MIN_MATCHED or not rounded:
        return None
    minutes, count = rounded.most_common(1)[0]
    if minutes == 0 or count < AGREEMENT * len(deltas):
        return None
    return timedelta(minutes=minutes)


def plan_redate(
    session: Session,
    *,
    since: datetime,
    now: datetime,
    feeds: FeedReader | None,
    pages: PageReader | None = None,
    verify: int = 0,
    seed: int = 0,
) -> RedatePlan:
    plan = RedatePlan(since=since)
    rows = session.execute(
        select(Item, Source)
        .options(defer(Item.body), defer(Item.summary))  # loaded only for a dateline
        .join(Source, Source.id == Item.source_id)
        .where(Item.first_seen_at >= since)
        .order_by(Source.key, Item.id)
    ).tuples()
    by_source: dict[int, tuple[Source, list[Item]]] = {}
    for item, source in rows:
        by_source.setdefault(source.id, (source, []))[1].append(item)
    sampler = random.Random(seed)
    for source, items in by_source.values():
        repair = SourceRepair(key=source.key, name=source.name, items=len(items))
        plan.sources.append(repair)
        tz = source_timezone(str(source.region), source.config)
        fresh: dict[str, datetime | None] = {}
        if feeds is not None and source.access_method == AccessMethod.FEED:
            try:
                fresh = {
                    stable_key(raw.stable_id or raw.url): raw.published_at
                    for raw in feeds(source, now)
                }
            except Exception as exc:  # noqa: BLE001 - one unreachable feed must not stop the repair
                repair.error = f"{type(exc).__name__}: {exc}"[:200]
        new: dict[int, datetime | None] = {}
        deltas: list[timedelta] = []
        for item in items:
            date = plausible(fresh.get(item.stable_id), seen=item.first_seen_at, tz=tz)
            if date is not None:  # a feed that now shows a later (edited) date is no evidence
                repair.matched += 1
                if item.published_at is not None:
                    deltas.append(item.published_at - date)
                new[item.id] = earliest(
                    plausible(item.published_at, seen=item.first_seen_at, tz=tz), date
                )
        repair.shift = _modal_shift(deltas)
        for item in items:
            if item.id in new:
                date = new[item.id]
            elif repair.shift is not None and item.published_at is not None:
                date = item.published_at - repair.shift
            else:
                date = item.published_at
            checked = plausible(date, seen=item.first_seen_at, tz=tz)
            if checked is None and date is not None:
                repair.dropped += 1
            if checked is None:
                checked = stated_date(item.body or item.summary, seen=item.first_seen_at, tz=tz)
                repair.from_text += checked is not None
            new[item.id] = checked
        for item in items:
            if new[item.id] != item.published_at:
                plan.changes[item.id] = new[item.id]
                repair.changed += 1
        moved = [item for item in items if item.id in plan.changes]
        if pages is not None and verify and moved:  # check the dates the repair would change
            _verify(repair, new, pages, tz, sampler.sample(moved, min(verify, len(moved))))
    return plan


def _verify(
    repair: SourceRepair,
    new: dict[int, datetime | None],
    pages: PageReader,
    tz: tzinfo,
    sample: list[Item],
) -> None:
    for item in sample:
        try:
            truth = pages(item.url, tz)
        except Exception:  # noqa: BLE001 - blocked or gone pages are skipped, not counted
            continue
        if truth is None:
            continue
        repair.checked += 1
        before, after = item.published_at or item.first_seen_at, new[item.id] or item.first_seen_at
        repair.right_before += abs(before - truth) <= TOLERANCE
        repair.right_after += abs(after - truth) <= TOLERANCE


def apply_redate(session: Session, plan: RedatePlan) -> int:
    for item_id, date in plan.changes.items():
        item = session.get(Item, item_id)
        if item is not None:
            item.published_at = date
    session.flush()
    return plan.changed


def summary(plan: RedatePlan) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for repair in plan.sources:
        for name in ("items", "changed", "matched", "dropped", "from_text", "checked"):
            totals[name] += getattr(repair, name)
        totals["right_before"] += repair.right_before
        totals["right_after"] += repair.right_after
        totals["shifted_sources"] += repair.shift is not None
    return dict(totals)
