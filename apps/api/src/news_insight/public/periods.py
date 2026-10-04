"""Reader time windows: rolling (1d·7d·30d·all) for the feed, KST calendar periods for the radar."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, get_args
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

Kind = Literal["day", "week", "month", "quarter"]
Rolling = Literal["1d", "7d", "30d", "all"]
KINDS: tuple[str, ...] = get_args(Kind)
ROLLING_DAYS = {"1d": 1, "7d": 7, "30d": 30}


class PeriodError(ValueError):
    """An unknown period kind or a malformed key."""


@dataclass(frozen=True)
class Window:
    """[start, end) in KST. Calendar windows carry their key and neighbours."""

    kind: str
    key: str
    start: datetime | None
    end: datetime

    @property
    def prev_key(self) -> str:
        return self.previous().key

    @property
    def next_key(self) -> str:
        return _shift(self, 1).key

    def previous(self) -> "Window":
        return _shift(self, -1)


def _start_of(kind: str, day: date) -> date:
    if kind == "day":
        return day
    if kind == "week":
        return day - timedelta(days=day.weekday())
    if kind == "month":
        return day.replace(day=1)
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _next_start(kind: str, start: date) -> date:
    if kind == "day":
        return start + timedelta(days=1)
    if kind == "week":
        return start + timedelta(weeks=1)
    return _add_months(start, 1 if kind == "month" else 3)


def _key(kind: str, start: date) -> str:
    if kind == "day":
        return start.isoformat()
    if kind == "week":
        year, week, _ = start.isocalendar()
        return f"{year}-W{week:02d}"
    if kind == "month":
        return f"{start.year}-{start.month:02d}"
    return f"{start.year}-Q{(start.month - 1) // 3 + 1}"


def _calendar(kind: str, start: date) -> Window:
    end = _next_start(kind, start)
    return Window(
        kind=kind,
        key=_key(kind, start),
        start=datetime.combine(start, datetime.min.time(), tzinfo=KST),
        end=datetime.combine(end, datetime.min.time(), tzinfo=KST),
    )


def _parse_start(kind: str, key: str) -> date:
    try:
        if kind == "day" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", key):
            return date.fromisoformat(key)
        if kind == "week" and (match := re.fullmatch(r"(\d{4})-W(\d{2})", key)):
            year, week = int(match[1]), int(match[2])
            return date.fromisocalendar(year, week, 1)
        if kind == "month" and (match := re.fullmatch(r"(\d{4})-(\d{2})", key)):
            return date(int(match[1]), int(match[2]), 1)
        if kind == "quarter" and (match := re.fullmatch(r"(\d{4})-Q([1-4])", key)):
            return date(int(match[1]), 3 * (int(match[2]) - 1) + 1, 1)
    except ValueError as error:
        raise PeriodError(f"invalid {kind} key '{key}'") from error
    raise PeriodError(f"invalid {kind} key '{key}'")


def calendar_window(kind: str, key: str) -> Window:
    if kind not in KINDS:
        raise PeriodError(f"unknown period '{kind}' (expected one of {', '.join(KINDS)})")
    return _calendar(kind, _parse_start(kind, key))


def current_key(kind: str, now: datetime) -> str:
    if kind not in KINDS:
        raise PeriodError(f"unknown period '{kind}'")
    return _key(kind, _start_of(kind, now.astimezone(KST).date()))


def trailing_windows(window: Window, count: int) -> list[Window]:
    """The `count` windows ending with `window`, oldest first."""
    windows = [window]
    while len(windows) < count:
        windows.insert(0, windows[0].previous())
    return windows


def rolling_window(period: str, now: datetime) -> Window:
    if period == "all":
        return Window(kind="all", key="all", start=None, end=now)
    if period not in ROLLING_DAYS:
        raise PeriodError(f"unknown period '{period}' (expected 1d, 7d, 30d or all)")
    return Window(
        kind=period, key=period, start=now - timedelta(days=ROLLING_DAYS[period]), end=now
    )


def _shift(window: Window, steps: int) -> Window:
    if window.kind in ROLLING_DAYS:
        span = timedelta(days=ROLLING_DAYS[window.kind]) * steps
        assert window.start is not None
        return Window(
            kind=window.kind, key=window.key, start=window.start + span, end=window.end + span
        )
    if window.kind == "all" or window.start is None:
        return window
    start = window.start.date()
    if steps < 0:
        target = _start_of(window.kind, start - timedelta(days=1))
    else:
        target = _next_start(window.kind, start)
    return _calendar(window.kind, target)
