"""The article's own date: source time zones, implausible dates and datelines in the text.

Collection time (`first_seen_at`) is when we saw an item; `published_at` is when the source
says it was written. Trends and lists read the article date (`Item.occurred_at`), so a wrong
`published_at` moves an item to the wrong day. Three faults seen in production (2026-10-27):

- feeds of Korean and Chinese outlets write "2026-10-27 08:09:31" without a zone, which
  feedparser reads as UTC: 26,638 news items landed 8-9 hours in the future;
- a sitemap (ZOL) labels Beijing wall-clock time with "Z";
- feeds that bump pubDate on every edit (t3n) moved items up to 20 days later on revisions.
"""

import re
from collections.abc import Mapping
from datetime import UTC, datetime, time, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

# a source's default zone by region; `config.timezone` overrides it
REGION_TIMEZONES = {
    "kr": "Asia/Seoul",
    "jp": "Asia/Tokyo",
    "greater_china": "Asia/Shanghai",
}
# clocks and feeds disagree by a few minutes; anything later than this is not a real date
FUTURE_SLACK = timedelta(minutes=15)
# a date without a time ("2026-10-27", papers and patents) names a day, which may not have begun
# everywhere when we see it
DAY_SLACK = timedelta(days=1)
# a verified date within this of the page's own date counts as right, and a page whose dates
# differ by more contradicts itself
TOLERANCE = timedelta(minutes=10)
# a date before this is a parse error (epoch zero, two-digit years), never an article date
EARLIEST = datetime(1990, 1, 1, tzinfo=UTC)


def source_timezone(region: str | None, config: Mapping[str, Any] | None = None) -> ZoneInfo:
    name = (config or {}).get("timezone") or REGION_TIMEZONES.get(str(region or ""), "UTC")
    try:
        return ZoneInfo(str(name))
    except (ValueError, KeyError):
        return ZoneInfo("UTC")


def plausible(published: datetime | None, *, seen: datetime, tz: tzinfo) -> datetime | None:
    """`published` when it can be the article's date, corrected when it is the source's wall
    clock read as UTC, None when it cannot be right (later than when we saw it)."""
    if published is None:
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    if published < EARLIEST:
        return None
    if published <= seen + FUTURE_SLACK:
        return published
    if _midnight(published, tz) and published <= seen + DAY_SLACK:
        return published
    offset = tz.utcoffset(published.replace(tzinfo=None)) or timedelta(0)
    if offset > timedelta(0) and published - offset <= seen + FUTURE_SLACK:
        return published - offset
    return None


def _midnight(moment: datetime, tz: tzinfo) -> bool:
    return any(
        (local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0)
        for local in (moment.astimezone(UTC), moment.astimezone(tz))
    )


def earliest(stored: datetime | None, incoming: datetime | None) -> datetime | None:
    """A revision keeps the first date: feeds that bump pubDate on every edit would otherwise
    move a report to the day of its last correction."""
    if stored is None or incoming is None:
        return stored or incoming
    return min(stored, incoming)


# datelines news sites put at the head or foot of the text: "입력 2026.10.26 14:30",
# "기사입력 2026-10-26 오후 2:30", "2026년 10월 26일 14:30", "2026年10月26日 14:30",
# "Published: 2026-10-26T14:30"
_DATELINE = re.compile(
    r"(?:입력|등록|발행|게재|송고|기사입력|최초\s*입력|발표|Published|Posted|发布(?:时间)?|発行|公開)"
    r"(?:일시|일자|일|시간)?\s*[:：]?\s*"
    r"(?P<y>20\d{2})\s*[-./년年]\s*(?P<m>\d{1,2})\s*[-./월月]\s*(?P<d>\d{1,2})\s*[일日]?\.?"
    r"(?:\s*T?\s*(?P<ampm>오전|오후|AM|PM)?\s*(?P<H>\d{1,2})\s*[:시]\s*(?P<M>\d{2}))?",
    re.IGNORECASE,
)


def stated_date(text: str | None, *, seen: datetime, tz: tzinfo) -> datetime | None:
    """The publication dateline written in the article text, in the source's zone, when there
    is one and it is plausible."""
    if not text:
        return None
    match = _DATELINE.search(text[:4000])
    if match is None:
        tail = text[-1500:]
        match = _DATELINE.search(tail)
    if match is None:
        return None
    hour = int(match["H"]) if match["H"] else 0
    minute = int(match["M"]) if match["M"] else 0
    ampm = (match["ampm"] or "").upper()
    if ampm in {"오후", "PM"} and hour < 12:
        hour += 12
    elif ampm in {"오전", "AM"} and hour == 12:
        hour = 0
    try:
        local = datetime(int(match["y"]), int(match["m"]), int(match["d"]), hour, minute)
    except ValueError:
        return None
    moment = local.replace(tzinfo=tz).astimezone(UTC)
    return moment if EARLIEST <= moment <= seen + FUTURE_SLACK else None


def page_date(
    stored: datetime | None,
    dates: list[datetime],
    *,
    seen: datetime,
    tz: tzinfo,
    offset_only: bool,
) -> datetime | None:
    """The page's own date when it replaces the stored one, else None.

    Only an earlier date counts: a lastmod, a crawl time or a feed's local wall clock read as
    UTC are all later than the publication, while pages that relabel local time as UTC or show
    their last edit are later too and must not move a right date. `offset_only` (feeds) takes
    the page only when it is exactly the source's UTC offset earlier."""
    if not dates or dates[-1] - dates[0] > TOLERANCE:
        return None  # no date, or the page contradicts itself
    truth = dates[0]
    if plausible(truth, seen=seen, tz=tz) != truth:
        return None
    if stored is None:
        return None if offset_only else truth
    if truth >= stored - TOLERANCE:
        return None
    if offset_only:
        offset = stored.astimezone(tz).utcoffset()
        return truth if offset and abs(stored - truth - offset) <= timedelta(minutes=1) else None
    return None if _same_day(truth, stored, tz) else truth


def _same_day(truth: datetime, stored: datetime, tz: tzinfo) -> bool:
    """A page that gives only a day (midnight in its zone or in UTC) on the stored date: the
    stored time is no worse than a midnight."""
    for zone in (tz, UTC):
        local = truth.astimezone(zone)
        if local.time() == time() and stored.astimezone(zone).date() == local.date():
            return True
    return False
