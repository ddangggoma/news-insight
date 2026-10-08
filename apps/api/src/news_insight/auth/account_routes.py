"""Account API (plan 14), internal like the rest of /api/admin: only the web server calls it.

The web server forwards the browser's address and user agent in X-Client-IP / X-Client-UA
(Caddy is the only way in, so the forwarded address is the real one). Admin routes also take
the admin's session token in X-Session-Token and check the role here, not only in the web.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from news_insight.auth import accounts, mailer
from news_insight.auth.accounts import ActionError, Client, FormError, LoginOutcome, Throttled
from news_insight.auth.models import AuthEvent, Role, User, UserStatus
from news_insight.config import Settings, get_settings
from news_insight.console.auth import require_console_key
from news_insight.db import get_db

log = logging.getLogger(__name__)

router = APIRouter(tags=["accounts"], dependencies=[Depends(require_console_key)])
DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


def _now() -> datetime:
    return datetime.now(UTC)


def client(
    x_client_ip: Annotated[str | None, Header()] = None,
    x_client_ua: Annotated[str | None, Header()] = None,
) -> Client:
    return Client(ip=x_client_ip or None, user_agent=x_client_ua or None)


ClientInfo = Annotated[Client, Depends(client)]


class SignupIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    name: str = Field(max_length=100)


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class TokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class PasswordIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    current: str = Field(max_length=256)
    password: str = Field(max_length=256)


class RoleIn(BaseModel):
    role: Role


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: Role
    status: UserStatus
    must_change_password: bool
    locked: bool
    created_at: datetime
    reviewed_at: datetime | None
    last_login_at: datetime | None

    @classmethod
    def of(cls, user: User, now: datetime) -> "UserOut":
        return cls(
            id=user.id,
            username=user.username,
            name=user.name,
            role=user.role,
            status=user.status,
            must_change_password=user.must_change_password,
            locked=user.locked_until is not None and user.locked_until > now,
            created_at=user.created_at,
            reviewed_at=user.reviewed_at,
            last_login_at=user.last_login_at,
        )


class SessionOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut


class SignupOut(BaseModel):
    status: Literal["pending"] = "pending"


class UsersOut(BaseModel):
    items: list[UserOut]
    counts: dict[str, int]


class TemporaryPassword(BaseModel):
    temporary_password: str


class EventOut(BaseModel):
    id: int
    at: datetime
    event: str
    actor_id: int | None
    ip: str | None
    user_agent: str | None

    @classmethod
    def of(cls, event: AuthEvent) -> "EventOut":
        return cls(
            id=event.id,
            at=event.at,
            event=event.event,
            actor_id=event.actor_id,
            ip=event.ip,
            user_agent=event.user_agent,
        )


def _form_error(error: FormError) -> HTTPException:
    return HTTPException(
        status.HTTP_400_BAD_REQUEST, {"field": error.field, "message": error.message}
    )


THROTTLED = HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts")


def _notify_signup(settings: Settings, *, username: str, name: str) -> None:
    url = f"{settings.public_base_url.rstrip('/')}/console/users"
    sent = mailer.send_email(
        settings,
        to=settings.admin_email,
        subject=f"[DX 인텔리전스] 가입 승인 요청: {name} ({username})",
        body=(
            f"새 가입 신청이 들어왔습니다.\n\n이름: {name}\n아이디: {username}\n\n"
            f"운영 콘솔 → 사용자에서 승인하거나 거절하세요.\n{url}\n"
        ),
    )
    if not sent:
        log.info("sign-up notice not mailed (SMTP not configured or delivery failed)")


# --- the visitor's own account -----------------------------------------------------------------


@router.post("/api/admin/accounts/signup", status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupIn, db: DB, settings: Config, who: ClientInfo, background: BackgroundTasks
) -> SignupOut:
    try:
        user = accounts.register(
            db,
            username=body.username,
            password=body.password,
            name=body.name,
            now=_now(),
            client=who,
        )
    except FormError as error:
        raise _form_error(error) from None
    except Throttled:
        raise THROTTLED from None
    db.commit()
    background.add_task(_notify_signup, settings, username=user.username, name=user.name)
    return SignupOut()


@router.post("/api/admin/accounts/login", response_model=None)
def login(body: LoginIn, db: DB, who: ClientInfo) -> SessionOut | JSONResponse:
    now = _now()
    result = accounts.authenticate(
        db, username=body.username, password=body.password, now=now, client=who
    )
    if result.outcome == LoginOutcome.OK and result.user is not None:
        issued = accounts.issue_session(db, result.user, now=now, client=who)
        db.commit()
        return SessionOut(
            token=issued.token, expires_at=issued.expires_at, user=UserOut.of(result.user, now)
        )
    db.commit()  # failure counters, lockouts and the audit trail
    code = {
        LoginOutcome.INVALID: status.HTTP_401_UNAUTHORIZED,
        LoginOutcome.THROTTLED: status.HTTP_429_TOO_MANY_REQUESTS,
    }.get(result.outcome, status.HTTP_403_FORBIDDEN)
    return JSONResponse({"outcome": result.outcome.value}, status_code=code)


@router.post("/api/admin/accounts/session")
def whoami(body: TokenIn, db: DB) -> UserOut:
    now = _now()
    user = accounts.check_session(db, token=body.token, now=now)
    db.commit()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no session")
    return UserOut.of(user, now)


@router.post("/api/admin/accounts/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: TokenIn, db: DB, who: ClientInfo) -> None:
    now = _now()
    user_id = accounts.revoke_session(db, token=body.token, now=now)
    if user_id is not None:
        accounts.record(db, "logout", now=now, client=who, user_id=user_id)
    db.commit()


@router.post("/api/admin/accounts/logout-others", status_code=status.HTTP_204_NO_CONTENT)
def logout_others(body: TokenIn, db: DB, who: ClientInfo) -> None:
    now = _now()
    user = accounts.check_session(db, token=body.token, now=now)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no session")
    accounts.revoke_all(db, user.id, now=now, keep=body.token)
    accounts.record(db, "logout_others", now=now, client=who, user_id=user.id)
    db.commit()


@router.post("/api/admin/accounts/password")
def change_password(body: PasswordIn, db: DB, who: ClientInfo) -> SessionOut:
    now = _now()
    user = accounts.check_session(db, token=body.token, now=now)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no session")
    try:
        accounts.change_password(
            db, user, current=body.current, new=body.password, now=now, client=who
        )
    except FormError as error:
        raise _form_error(error) from None
    issued = accounts.issue_session(db, user, now=now, client=who)
    db.commit()
    return SessionOut(token=issued.token, expires_at=issued.expires_at, user=UserOut.of(user, now))


# --- admin: user approval ----------------------------------------------------------------------


def require_admin(db: DB, x_session_token: Annotated[str | None, Header()] = None) -> User:
    user = accounts.check_session(db, token=x_session_token or "", now=_now())
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no session")
    if user.role != Role.ADMIN or user.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


Admin = Annotated[User, Depends(require_admin)]


@router.get("/api/admin/users")
def list_users(
    db: DB, admin: Admin, status_: Annotated[UserStatus | None, Query(alias="status")] = None
) -> UsersOut:
    now = _now()
    return UsersOut(
        items=[UserOut.of(user, now) for user in accounts.list_users(db, status_)],
        counts=accounts.status_counts(db),
    )


@router.get("/api/admin/users/{user_id}")
def get_user(user_id: int, db: DB, admin: Admin) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such user")
    return UserOut.of(user, _now())


@router.get("/api/admin/users/{user_id}/events")
def user_events(user_id: int, db: DB, admin: Admin) -> list[EventOut]:
    return [EventOut.of(event) for event in accounts.user_events(db, user_id)]


@router.post("/api/admin/users/{user_id}/role")
def set_role(user_id: int, body: RoleIn, db: DB, admin: Admin, who: ClientInfo) -> UserOut:
    now = _now()
    try:
        user = accounts.set_role(db, admin, user_id, body.role, now=now, client=who)
    except ActionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    db.commit()
    return UserOut.of(user, now)


@router.post("/api/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, db: DB, admin: Admin, who: ClientInfo) -> TemporaryPassword:
    try:
        temporary = accounts.reset_password(db, admin, user_id, now=_now(), client=who)
    except ActionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    db.commit()
    return TemporaryPassword(temporary_password=temporary)


# the generic action route last: FastAPI does not fall through to a later route on a 422
ACTIONS = {
    "approve": accounts.approve,
    "reject": accounts.reject,
    "suspend": accounts.suspend,
    "reactivate": accounts.reactivate,
}


@router.post("/api/admin/users/{user_id}/{action}")
def act(
    user_id: int,
    action: Literal["approve", "reject", "suspend", "reactivate", "unlock"],
    db: DB,
    admin: Admin,
    who: ClientInfo,
) -> UserOut:
    now = _now()
    try:
        if action == "unlock":
            user = accounts.unlock(db, admin, user_id, now=now)
        else:
            user = ACTIONS[action](db, admin, user_id, now=now, client=who)
    except ActionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    db.commit()
    return UserOut.of(user, now)
