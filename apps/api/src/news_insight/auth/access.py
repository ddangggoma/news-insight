"""Access log: who opened what, when and from where (console → 접속 기록).

The web server's proxy sees every request of a signed-in account and sends them here in
batches, so a page load costs no extra API call. Logins, failed logins and logouts are already
in auth_events; the console reads both. Rows past ACCESS_KEEP go with the nightly auth purge.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Select, func, insert, select
from sqlalchemy.orm import Session

from news_insight.auth.models import AccessKind, AccessLog, AuthEvent, User

ACCESS_KEEP = timedelta(days=30)
LATE = timedelta(days=1)  # older entries in a batch are stamped with the arrival time
EARLY = timedelta(minutes=1)
LOGIN_EVENTS: dict[str, tuple[str, ...]] = {
    "ok": ("login_ok",),
    "fail": (
        "login_fail",
        "login_locked",
        "locked",
        "login_pending",
        "login_rejected",
        "login_suspended",
    ),
    "logout": ("logout", "logout_others"),
}


@dataclass(frozen=True)
class Entry:
    at: datetime
    user_id: int
    kind: AccessKind
    method: str
    path: str
    query: str | None = None
    ip: str | None = None


@dataclass(frozen=True)
class Window:
    """Whole days in the site's time zone, both ends included; None leaves that end open."""

    since: date | None = None
    until: date | None = None
    tz: str = "Asia/Seoul"

    def start(self) -> datetime | None:
        if self.since is None:
            return None
        return datetime.combine(self.since, time.min, ZoneInfo(self.tz))

    def end(self) -> datetime | None:
        if self.until is None:
            return None
        return datetime.combine(self.until + timedelta(days=1), time.min, ZoneInfo(self.tz))


@dataclass(frozen=True)
class Filters:
    user_id: int | None = None
    ip: str | None = None  # prefix: "203.0.113." matches the whole range
    window: Window = Window()


def record(session: Session, entries: Sequence[Entry], *, now: datetime) -> int:
    """Store a batch; entries of accounts that no longer exist are dropped."""
    if not entries:
        return 0
    wanted = {entry.user_id for entry in entries}
    known = set(session.scalars(select(User.id).where(User.id.in_(wanted))))
    rows: list[dict[str, Any]] = []
    for entry in entries:
        if entry.user_id not in known:
            continue
        at = entry.at if entry.at.tzinfo else entry.at.replace(tzinfo=now.tzinfo)
        if at > now + EARLY or at < now - LATE:
            at = now
        rows.append(
            {
                "at": at,
                "user_id": entry.user_id,
                "kind": entry.kind,
                "method": entry.method.upper()[:8],
                "path": entry.path[:300] or "/",
                "query": entry.query[:500] if entry.query else None,
                "ip": entry.ip[:45] if entry.ip else None,
            }
        )
    if rows:
        session.execute(insert(AccessLog), rows)
    return len(rows)


def _within(column: Any, window: Window) -> list[ColumnElement[bool]]:
    start, end = window.start(), window.end()
    return [
        *([column >= start] if start is not None else []),
        *([column < end] if end is not None else []),
    ]


def _page(session: Session, query: Select[Any], *, page: int, size: int) -> tuple[list[Any], int]:
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = session.execute(query.offset((page - 1) * size).limit(size)).tuples().all()
    return list(rows), int(total or 0)


def requests(
    session: Session,
    filters: Filters,
    *,
    kind: AccessKind | None = None,
    path: str | None = None,
    page: int = 1,
    size: int = 50,
) -> tuple[list[tuple[AccessLog, User]], int]:
    """Newest first, with the account (path is a prefix: "/console" covers the console)."""
    conditions = _within(AccessLog.at, filters.window)
    if filters.user_id is not None:
        conditions.append(AccessLog.user_id == filters.user_id)
    if filters.ip:
        conditions.append(AccessLog.ip.startswith(filters.ip, autoescape=True))
    if kind is not None:
        conditions.append(AccessLog.kind == kind)
    if path:
        conditions.append(AccessLog.path.startswith(path, autoescape=True))
    query = (
        select(AccessLog, User)
        .join(User, User.id == AccessLog.user_id)
        .where(*conditions)
        .order_by(AccessLog.at.desc(), AccessLog.id.desc())
    )
    return _page(session, query, page=page, size=size)


def logins(
    session: Session,
    filters: Filters,
    *,
    outcome: str | None = None,
    page: int = 1,
    size: int = 50,
) -> tuple[list[tuple[AuthEvent, User | None]], int]:
    """Logins, failed logins and logouts, newest first. A failure for an unknown username has
    no account (the attempted name is never stored: it may be a mistyped password)."""
    events = LOGIN_EVENTS.get(outcome or "") or tuple(e for g in LOGIN_EVENTS.values() for e in g)
    conditions = [AuthEvent.event.in_(events), *_within(AuthEvent.at, filters.window)]
    if filters.user_id is not None:
        conditions.append(AuthEvent.user_id == filters.user_id)
    if filters.ip:
        conditions.append(AuthEvent.ip.startswith(filters.ip, autoescape=True))
    query = (
        select(AuthEvent, User)
        .outerjoin(User, User.id == AuthEvent.user_id)
        .where(*conditions)
        .order_by(AuthEvent.at.desc(), AuthEvent.id.desc())
    )
    return _page(session, query, page=page, size=size)


@dataclass(frozen=True)
class Usage:
    user: User
    requests: int = 0
    pages: int = 0
    actions: int = 0
    ips: int = 0
    last_at: datetime | None = None
    last_ip: str | None = None
    logins: int = 0
    failures: int = 0


def usage(session: Session, filters: Filters) -> list[Usage]:
    """Per account over the window: requests, distinct addresses, last visit, logins."""
    access = [*_within(AccessLog.at, filters.window)]
    auth = [*_within(AuthEvent.at, filters.window)]
    if filters.user_id is not None:
        access.append(AccessLog.user_id == filters.user_id)
        auth.append(AuthEvent.user_id == filters.user_id)
    if filters.ip:
        access.append(AccessLog.ip.startswith(filters.ip, autoescape=True))
        auth.append(AuthEvent.ip.startswith(filters.ip, autoescape=True))
    counts = session.execute(
        select(
            AccessLog.user_id,
            func.count(),
            func.count().filter(AccessLog.kind == AccessKind.PAGE),
            func.count().filter(AccessLog.kind == AccessKind.ACTION),
            func.count(AccessLog.ip.distinct()),
            func.max(AccessLog.at),
        )
        .where(*access)
        .group_by(AccessLog.user_id)
    ).all()
    last_ips = dict(
        session.execute(
            select(AccessLog.user_id, AccessLog.ip)
            .where(*access)
            .distinct(AccessLog.user_id)
            .order_by(AccessLog.user_id, AccessLog.at.desc(), AccessLog.id.desc())
        )
        .tuples()
        .all()
    )
    signed = session.execute(
        select(
            AuthEvent.user_id,
            func.count().filter(AuthEvent.event.in_(LOGIN_EVENTS["ok"])),
            func.count().filter(AuthEvent.event.in_(LOGIN_EVENTS["fail"])),
        )
        .where(AuthEvent.user_id.is_not(None), *auth)
        .group_by(AuthEvent.user_id)
    ).all()
    stats: dict[int, dict[str, Any]] = {}
    for user_id, total, pages, actions, ips, last_at in counts:
        stats[user_id] = {
            "requests": int(total),
            "pages": int(pages),
            "actions": int(actions),
            "ips": int(ips),
            "last_at": last_at,
            "last_ip": last_ips.get(user_id),
        }
    for user_id, ok, failed in signed:
        if ok or failed:
            stats.setdefault(user_id, {}).update(logins=int(ok), failures=int(failed))
    if not stats:
        return []
    users = {u.id: u for u in session.scalars(select(User).where(User.id.in_(stats)))}
    found = [Usage(user=users[uid], **values) for uid, values in stats.items() if uid in users]
    epoch = datetime.min.replace(tzinfo=UTC)
    return sorted(found, key=lambda u: (u.last_at or epoch, u.requests), reverse=True)


@dataclass(frozen=True)
class PathCount:
    path: str
    kind: AccessKind
    count: int
    last_at: datetime


def top_paths(session: Session, filters: Filters, *, limit: int = 15) -> list[PathCount]:
    """The most used pages and calls over the window (one account, or everyone)."""
    conditions = _within(AccessLog.at, filters.window)
    if filters.user_id is not None:
        conditions.append(AccessLog.user_id == filters.user_id)
    if filters.ip:
        conditions.append(AccessLog.ip.startswith(filters.ip, autoescape=True))
    rows = session.execute(
        select(AccessLog.path, AccessLog.kind, func.count(), func.max(AccessLog.at))
        .where(*conditions)
        .group_by(AccessLog.path, AccessLog.kind)
        .order_by(func.count().desc(), func.max(AccessLog.at).desc())
        .limit(limit)
    ).all()
    return [PathCount(path, kind, int(count), last_at) for path, kind, count, last_at in rows]
