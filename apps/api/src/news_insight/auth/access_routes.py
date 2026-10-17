"""Access log API (console → 접속 기록), internal like the rest of /api/admin.

The web server posts batches with the console key alone; the reads also need an admin session
(X-Session-Token), like the user approval routes.
"""

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from news_insight.auth import access
from news_insight.auth.account_routes import Admin
from news_insight.auth.models import AccessKind, Role, User
from news_insight.config import Settings, get_settings
from news_insight.console.auth import require_console_key
from news_insight.console.schemas import Page
from news_insight.db import get_db

router = APIRouter(tags=["access"], dependencies=[Depends(require_console_key)])
DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
PageQ = Annotated[int, Query(ge=1)]
SizeQ = Annotated[int, Query(ge=1, le=200)]
BATCH_MAX = 500


class EntryIn(BaseModel):
    at: datetime
    user_id: int
    kind: AccessKind
    method: str = Field(min_length=1, max_length=16)
    path: str = Field(min_length=1, max_length=2000)
    query: str | None = Field(default=None, max_length=4000)
    ip: str | None = Field(default=None, max_length=100)


class BatchIn(BaseModel):
    entries: list[EntryIn] = Field(max_length=BATCH_MAX)


class Recorded(BaseModel):
    recorded: int


class Account(BaseModel):
    id: int
    username: str
    name: str
    role: Role


class RequestOut(BaseModel):
    id: int
    at: datetime
    user: Account
    kind: AccessKind
    method: str
    path: str
    query: str | None
    ip: str | None


class LoginOut(BaseModel):
    id: int
    at: datetime
    event: str
    user: Account | None
    ip: str | None
    user_agent: str | None


class UsageOut(BaseModel):
    user: Account
    requests: int
    pages: int
    actions: int
    ips: int
    last_at: datetime | None
    last_ip: str | None
    logins: int
    failures: int


class PathOut(BaseModel):
    path: str
    kind: AccessKind
    count: int
    last_at: datetime


class UsageReport(BaseModel):
    accounts: list[UsageOut]
    paths: list[PathOut]
    keep_days: int = access.ACCESS_KEEP.days


def _account(user: User) -> Account:
    return Account(id=user.id, username=user.username, name=user.name, role=user.role)


def filters(
    settings: Config,
    user_id: Annotated[int | None, Query(alias="user")] = None,
    ip: Annotated[str | None, Query(max_length=45)] = None,
    since: date | None = None,
    until: date | None = None,
) -> access.Filters:
    return access.Filters(
        user_id=user_id,
        ip=(ip or "").strip() or None,
        window=access.Window(since=since, until=until, tz=settings.timezone),
    )


Filtered = Annotated[access.Filters, Depends(filters)]


@router.post("/api/admin/access-log")
def record(body: BatchIn, db: DB) -> Recorded:
    entries = [access.Entry(**entry.model_dump()) for entry in body.entries]
    recorded = access.record(db, entries, now=datetime.now(UTC))
    db.commit()
    return Recorded(recorded=recorded)


@router.get("/api/admin/access-log/requests")
def list_requests(
    db: DB,
    admin: Admin,
    where: Filtered,
    kind: AccessKind | None = None,
    path: Annotated[str | None, Query(max_length=300)] = None,
    page: PageQ = 1,
    size: SizeQ = 50,
) -> Page[RequestOut]:
    rows, total = access.requests(
        db, where, kind=kind, path=(path or "").strip() or None, page=page, size=size
    )
    items = [
        RequestOut(
            id=log.id,
            at=log.at,
            user=_account(user),
            kind=log.kind,
            method=log.method,
            path=log.path,
            query=log.query,
            ip=log.ip,
        )
        for log, user in rows
    ]
    return Page(items=items, total=total, page=page, size=size)


@router.get("/api/admin/access-log/logins")
def list_logins(
    db: DB,
    admin: Admin,
    where: Filtered,
    outcome: Literal["ok", "fail", "logout"] | None = None,
    page: PageQ = 1,
    size: SizeQ = 50,
) -> Page[LoginOut]:
    rows, total = access.logins(db, where, outcome=outcome, page=page, size=size)
    items = [
        LoginOut(
            id=event.id,
            at=event.at,
            event=event.event,
            user=_account(user) if user is not None else None,
            ip=event.ip,
            user_agent=event.user_agent,
        )
        for event, user in rows
    ]
    return Page(items=items, total=total, page=page, size=size)


@router.get("/api/admin/access-log/usage")
def usage(db: DB, admin: Admin, where: Filtered) -> UsageReport:
    accounts = [
        UsageOut(
            user=_account(row.user),
            requests=row.requests,
            pages=row.pages,
            actions=row.actions,
            ips=row.ips,
            last_at=row.last_at,
            last_ip=row.last_ip,
            logins=row.logins,
            failures=row.failures,
        )
        for row in access.usage(db, where)
    ]
    paths = [
        PathOut(path=row.path, kind=row.kind, count=row.count, last_at=row.last_at)
        for row in access.top_paths(db, where)
    ]
    return UsageReport(accounts=accounts, paths=paths)
