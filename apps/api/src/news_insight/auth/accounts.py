"""Site accounts (plan 14): sign-up, admin approval, username/password login and sessions.

Only `active` accounts can log in. A wrong password never reveals whether the username
exists or what state the account is in; the state is told only to someone who knows the
password. Raw passwords and session tokens never touch the database or the audit trail.
"""

import hashlib
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from news_insight.auth import passwords
from news_insight.auth.models import AuthEvent, Role, User, UserSession, UserStatus

SESSION_TTL = timedelta(days=14)  # absolute
IDLE_TTL = timedelta(days=3)  # since the session was last used
SEEN_RESOLUTION = timedelta(minutes=5)
LOCK_AFTER = 5  # consecutive failures
LOCK_BASE = timedelta(minutes=15)  # doubles with every further failure
LOCK_MAX = timedelta(hours=24)
IP_FAIL_WINDOW = timedelta(minutes=10)
IP_FAIL_LIMIT = 30  # failed logins per client IP and window
SIGNUP_WINDOW = timedelta(hours=1)
SIGNUP_LIMIT = 20  # sign-ups per client IP and window
PENDING_CAP = 50
REJECTED_KEEP = timedelta(days=30)
PENDING_KEEP = timedelta(days=90)
EVENTS_KEEP = timedelta(days=180)
USERNAME_RE = re.compile(r"[a-z0-9._-]{4,32}")
NAME_MAX = 50


class LoginOutcome(StrEnum):
    OK = "ok"
    INVALID = "invalid"  # unknown user, wrong password or locked: one answer for all three
    PENDING = "pending"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    THROTTLED = "throttled"


REFUSED = {
    UserStatus.PENDING: LoginOutcome.PENDING,
    UserStatus.REJECTED: LoginOutcome.REJECTED,
    UserStatus.SUSPENDED: LoginOutcome.SUSPENDED,
}


class FormError(Exception):
    """A user-facing validation error; `field` names the form field (None: the whole form)."""

    def __init__(self, field: str | None, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class Throttled(Exception):
    pass


class ActionError(Exception):
    """An admin action that does not apply to this account."""


@dataclass(frozen=True)
class Client:
    ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True)
class Issued:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class Login:
    outcome: LoginOutcome
    user: User | None = None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def record(
    session: Session,
    event: str,
    *,
    now: datetime,
    client: Client,
    user_id: int | None = None,
    actor_id: int | None = None,
) -> None:
    session.add(
        AuthEvent(
            at=now,
            event=event,
            user_id=user_id,
            actor_id=actor_id,
            ip=client.ip[:45] if client.ip else None,
            user_agent=client.user_agent[:200] if client.user_agent else None,
        )
    )


def _recent(session: Session, event: str, ip: str, since: datetime) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(AuthEvent)
            .where(AuthEvent.event == event, AuthEvent.ip == ip, AuthEvent.at >= since)
        )
        or 0
    )


def find_user(session: Session, username: str) -> User | None:
    return session.scalars(
        select(User).where(User.username == normalize_username(username))
    ).first()


def _clean_name(name: str) -> str:
    cleaned = unicodedata.normalize("NFC", name).strip()
    if not cleaned or len(cleaned) > NAME_MAX:
        raise FormError("name", f"이름을 1~{NAME_MAX}자로 입력하세요.")
    if any(unicodedata.category(ch).startswith("C") for ch in cleaned):
        raise FormError("name", "이름에 쓸 수 없는 문자가 있습니다.")
    return cleaned


def _check_username(session: Session, username: str) -> str:
    normalized = normalize_username(username)
    if not USERNAME_RE.fullmatch(normalized):
        raise FormError(
            "username",
            "아이디는 4~32자의 영문 소문자, 숫자, 마침표, 밑줄, 하이픈만 쓸 수 있습니다.",
        )
    if find_user(session, normalized) is not None:
        raise FormError("username", "이미 쓰고 있는 아이디입니다.")
    return normalized


def _check_password(password: str, *, username: str) -> None:
    error = passwords.policy_error(password, username=username)
    if error:
        raise FormError("password", error)


def register(
    session: Session,
    *,
    username: str,
    password: str,
    name: str,
    now: datetime,
    client: Client,
) -> User:
    """A new `pending` reader account. Raises FormError or Throttled."""
    if client.ip and _recent(session, "signup", client.ip, now - SIGNUP_WINDOW) >= SIGNUP_LIMIT:
        raise Throttled
    normalized = _check_username(session, username)
    cleaned = _clean_name(name)
    _check_password(password, username=normalized)
    pending = session.scalar(
        select(func.count()).select_from(User).where(User.status == UserStatus.PENDING)
    )
    if (pending or 0) >= PENDING_CAP:
        raise FormError(None, "지금은 가입 신청을 받을 수 없습니다. 관리자에게 문의하세요.")
    user = User(
        username=normalized,
        password_hash=passwords.hash_password(password),
        name=cleaned,
        role=Role.READER,
        status=UserStatus.PENDING,
        must_change_password=False,
        failed_count=0,
        created_at=now,
        password_changed_at=now,
    )
    session.add(user)
    session.flush()
    record(session, "signup", now=now, client=client, user_id=user.id)
    return user


def create_admin(
    session: Session, *, username: str, password: str, name: str, now: datetime
) -> User:
    """An active admin account (CLI bootstrap). Raises FormError."""
    normalized = _check_username(session, username)
    cleaned = _clean_name(name)
    _check_password(password, username=normalized)
    user = User(
        username=normalized,
        password_hash=passwords.hash_password(password),
        name=cleaned,
        role=Role.ADMIN,
        status=UserStatus.ACTIVE,
        must_change_password=False,
        failed_count=0,
        created_at=now,
        reviewed_at=now,
        password_changed_at=now,
    )
    session.add(user)
    session.flush()
    record(session, "create_admin", now=now, client=Client(), user_id=user.id)
    return user


def authenticate(
    session: Session, *, username: str, password: str, now: datetime, client: Client
) -> Login:
    if (
        client.ip
        and _recent(session, "login_fail", client.ip, now - IP_FAIL_WINDOW) >= IP_FAIL_LIMIT
    ):
        return Login(LoginOutcome.THROTTLED)
    user = find_user(session, username)
    if user is None:
        passwords.burn_time(password)
        record(session, "login_fail", now=now, client=client)
        return Login(LoginOutcome.INVALID)
    if user.locked_until is not None and user.locked_until > now:
        passwords.burn_time(password)
        record(session, "login_locked", now=now, client=client, user_id=user.id)
        return Login(LoginOutcome.INVALID)
    if not passwords.verify_password(user.password_hash, password):
        user.failed_count += 1
        if user.failed_count >= LOCK_AFTER:
            lock = LOCK_BASE * 2 ** (user.failed_count - LOCK_AFTER)
            user.locked_until = now + min(lock, LOCK_MAX)
            record(session, "locked", now=now, client=client, user_id=user.id)
        record(session, "login_fail", now=now, client=client, user_id=user.id)
        return Login(LoginOutcome.INVALID)
    user.failed_count = 0
    user.locked_until = None
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    refused = REFUSED.get(user.status)
    if refused is not None:
        record(session, f"login_{refused.value}", now=now, client=client, user_id=user.id)
        return Login(refused, user)
    user.last_login_at = now
    record(session, "login_ok", now=now, client=client, user_id=user.id)
    return Login(LoginOutcome.OK, user)


def issue_session(session: Session, user: User, *, now: datetime, client: Client) -> Issued:
    """A fresh token for every login: a cookie from before the login is never reused."""
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + SESSION_TTL,
            last_seen_at=now,
            ip=client.ip[:45] if client.ip else None,
            user_agent=client.user_agent[:200] if client.user_agent else None,
        )
    )
    session.flush()
    return Issued(token, now + SESSION_TTL)


def _live(session: Session, token: str, now: datetime) -> UserSession | None:
    if not token:
        return None
    entry = session.scalars(
        select(UserSession).where(UserSession.token_hash == hash_token(token))
    ).first()
    if (
        entry is None
        or entry.revoked_at is not None
        or entry.expires_at <= now
        or entry.last_seen_at <= now - IDLE_TTL
    ):
        return None
    return entry


def check_session(session: Session, *, token: str, now: datetime) -> User | None:
    """The active user behind a live session token, else None."""
    entry = _live(session, token, now)
    if entry is None:
        return None
    user = session.get(User, entry.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        return None
    if now - entry.last_seen_at >= SEEN_RESOLUTION:
        entry.last_seen_at = now
    return user


def revoke_session(session: Session, *, token: str, now: datetime) -> int | None:
    """Revoke one session; returns its user id (None if it was not live)."""
    entry = _live(session, token, now)
    if entry is None:
        return None
    entry.revoked_at = now
    return entry.user_id


def revoke_all(session: Session, user_id: int, *, now: datetime, keep: str | None = None) -> int:
    """Revoke every live session of a user, except the one whose token is `keep`."""
    query = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if keep:
        query = query.where(UserSession.token_hash != hash_token(keep))
    result = session.execute(query.values(revoked_at=now))
    return int(getattr(result, "rowcount", 0) or 0)


def change_password(
    session: Session, user: User, *, current: str, new: str, now: datetime, client: Client
) -> None:
    """Own password change. Every session of the user ends; the caller issues a new one."""
    if not passwords.verify_password(user.password_hash, current):
        raise FormError("current", "현재 비밀번호가 올바르지 않습니다.")
    if current == new:
        raise FormError("password", "지금과 다른 비밀번호를 쓰세요.")
    _check_password(new, username=user.username)
    user.password_hash = passwords.hash_password(new)
    user.must_change_password = False
    user.password_changed_at = now
    revoke_all(session, user.id, now=now)
    record(session, "password_change", now=now, client=client, user_id=user.id)


# --- admin actions -----------------------------------------------------------------------------


def _target(session: Session, admin: User | None, user_id: int) -> User:
    """The account an admin acts on (`admin` None: the CLI on the host)."""
    user = session.get(User, user_id)
    if user is None:
        raise ActionError("사용자를 찾을 수 없습니다.")
    if admin is not None and user.id == admin.id:
        raise ActionError("자기 계정에는 이 작업을 할 수 없습니다.")
    return user


def _actor(admin: User | None) -> int | None:
    return admin.id if admin is not None else None


def _other_active_admins(session: Session, user: User) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == Role.ADMIN,
                User.status == UserStatus.ACTIVE,
                User.id != user.id,
            )
        )
        or 0
    )


def _guard_last_admin(session: Session, user: User) -> None:
    active_admin = user.role == Role.ADMIN and user.status == UserStatus.ACTIVE
    if active_admin and _other_active_admins(session, user) == 0:
        raise ActionError("마지막 관리자는 정지하거나 일반 사용자로 바꿀 수 없습니다.")


def _expect(user: User, *allowed: UserStatus) -> None:
    if user.status not in allowed:
        raise ActionError("지금 상태에서는 할 수 없는 작업입니다.")


def approve(
    session: Session, admin: User | None, user_id: int, *, now: datetime, client: Client
) -> User:
    user = _target(session, admin, user_id)
    _expect(user, UserStatus.PENDING, UserStatus.REJECTED)
    user.status = UserStatus.ACTIVE
    user.reviewed_at, user.reviewed_by = now, _actor(admin)
    record(session, "approve", now=now, client=client, user_id=user.id, actor_id=_actor(admin))
    return user


def reject(
    session: Session, admin: User | None, user_id: int, *, now: datetime, client: Client
) -> User:
    user = _target(session, admin, user_id)
    _expect(user, UserStatus.PENDING)
    user.status = UserStatus.REJECTED
    user.reviewed_at, user.reviewed_by = now, _actor(admin)
    revoke_all(session, user.id, now=now)
    record(session, "reject", now=now, client=client, user_id=user.id, actor_id=_actor(admin))
    return user


def suspend(
    session: Session, admin: User | None, user_id: int, *, now: datetime, client: Client
) -> User:
    user = _target(session, admin, user_id)
    _expect(user, UserStatus.ACTIVE)
    _guard_last_admin(session, user)
    user.status = UserStatus.SUSPENDED
    revoke_all(session, user.id, now=now)
    record(session, "suspend", now=now, client=client, user_id=user.id, actor_id=_actor(admin))
    return user


def reactivate(
    session: Session, admin: User | None, user_id: int, *, now: datetime, client: Client
) -> User:
    user = _target(session, admin, user_id)
    _expect(user, UserStatus.SUSPENDED)
    user.status = UserStatus.ACTIVE
    record(session, "reactivate", now=now, client=client, user_id=user.id, actor_id=_actor(admin))
    return user


def set_role(
    session: Session, admin: User | None, user_id: int, role: Role, *, now: datetime, client: Client
) -> User:
    user = _target(session, admin, user_id)
    _expect(user, UserStatus.ACTIVE)
    if user.role == role:
        return user
    if role != Role.ADMIN:
        _guard_last_admin(session, user)
    user.role = role
    revoke_all(session, user.id, now=now)
    record(
        session,
        f"role_{role.value}",
        now=now,
        client=client,
        user_id=user.id,
        actor_id=_actor(admin),
    )
    return user


def reset_password(
    session: Session, admin: User | None, user_id: int, *, now: datetime, client: Client
) -> str:
    """A temporary password, returned once; the user must change it at the next login."""
    user = _target(session, admin, user_id)
    _expect(user, UserStatus.ACTIVE, UserStatus.SUSPENDED)
    temporary = secrets.token_urlsafe(12)
    user.password_hash = passwords.hash_password(temporary)
    user.must_change_password = True
    user.password_changed_at = now
    user.failed_count, user.locked_until = 0, None
    revoke_all(session, user.id, now=now)
    record(
        session, "password_reset", now=now, client=client, user_id=user.id, actor_id=_actor(admin)
    )
    return temporary


def unlock(session: Session, admin: User | None, user_id: int, *, now: datetime) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise ActionError("사용자를 찾을 수 없습니다.")
    user.failed_count, user.locked_until = 0, None
    record(
        session,
        "unlock",
        now=now,
        client=Client(),
        user_id=user.id,
        actor_id=_actor(admin),
    )
    return user


def list_users(session: Session, status: UserStatus | None = None) -> list[User]:
    query = select(User).order_by(User.created_at.desc())
    if status is not None:
        query = query.where(User.status == status)
    return list(session.scalars(query))


def status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(User.status, func.count()).group_by(User.status)).all()
    counts = {status.value: 0 for status in UserStatus}
    counts.update({status.value: int(count) for status, count in rows})
    return counts


def user_events(session: Session, user_id: int, *, limit: int = 100) -> list[AuthEvent]:
    return list(
        session.scalars(
            select(AuthEvent)
            .where(AuthEvent.user_id == user_id)
            .order_by(AuthEvent.at.desc(), AuthEvent.id.desc())
            .limit(limit)
        )
    )


def purge(session: Session, *, now: datetime) -> int:
    """Drop dead sessions, old rejections, stale sign-ups and audit rows past retention."""
    removed = 0
    for statement in (
        delete(UserSession).where(
            or_(
                UserSession.expires_at < now,
                UserSession.last_seen_at < now - IDLE_TTL,
                UserSession.revoked_at.is_not(None),
            )
        ),
        delete(User).where(
            User.status == UserStatus.REJECTED, User.reviewed_at < now - REJECTED_KEEP
        ),
        delete(User).where(User.status == UserStatus.PENDING, User.created_at < now - PENDING_KEEP),
        delete(AuthEvent).where(AuthEvent.at < now - EVENTS_KEEP),
    ):
        result = session.execute(statement)
        removed += int(getattr(result, "rowcount", 0) or 0)
    return removed
