"""Single-admin magic-link login (requirements §9).

Only `settings.admin_email` can receive a link. Links are single-use and expire after
LOGIN_TTL; consuming one opens a SESSION_TTL session. Raw tokens never touch the database.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from news_insight.auth.models import AdminToken, TokenKind

LOGIN_TTL = timedelta(minutes=15)
SESSION_TTL = timedelta(days=14)
RATE_WINDOW = timedelta(minutes=15)
RATE_LIMIT = 5  # login links per RATE_WINDOW
SEEN_RESOLUTION = timedelta(minutes=5)


@dataclass(frozen=True)
class Issued:
    token: str
    expires_at: datetime


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _issue(session: Session, kind: TokenKind, email: str, now: datetime, ttl: timedelta) -> Issued:
    token = secrets.token_urlsafe(32)
    session.add(
        AdminToken(
            kind=kind,
            token_hash=hash_token(token),
            email=email,
            created_at=now,
            expires_at=now + ttl,
        )
    )
    session.flush()
    return Issued(token, now + ttl)


def _find(session: Session, kind: TokenKind, token: str) -> AdminToken | None:
    if not token:
        return None
    return session.scalars(
        select(AdminToken).where(
            AdminToken.kind == kind, AdminToken.token_hash == hash_token(token)
        )
    ).first()


def purge_expired(session: Session, *, now: datetime) -> int:
    result = session.execute(delete(AdminToken).where(AdminToken.expires_at < now))
    return int(getattr(result, "rowcount", 0) or 0)


def issue_login(session: Session, *, email: str, admin_email: str, now: datetime) -> Issued | None:
    """A login link for the admin address, or None (other address, or rate limited)."""
    address = normalize_email(email)
    if not admin_email or address != normalize_email(admin_email):
        return None
    purge_expired(session, now=now)
    recent = session.scalar(
        select(func.count())
        .select_from(AdminToken)
        .where(AdminToken.kind == TokenKind.LOGIN, AdminToken.created_at >= now - RATE_WINDOW)
    )
    if (recent or 0) >= RATE_LIMIT:
        return None
    return _issue(session, TokenKind.LOGIN, address, now, LOGIN_TTL)


def consume_login(session: Session, *, token: str, now: datetime) -> Issued | None:
    """Exchange an unused, unexpired link for a new session (the link dies either way)."""
    login = _find(session, TokenKind.LOGIN, token)
    if login is None or login.used_at is not None:
        return None
    login.used_at = now
    if login.expires_at <= now:
        return None
    return _issue(session, TokenKind.SESSION, login.email, now, SESSION_TTL)


def check_session(session: Session, *, token: str, now: datetime) -> str | None:
    """The admin email for a live session token, else None."""
    entry = _find(session, TokenKind.SESSION, token)
    if entry is None or entry.used_at is not None or entry.expires_at <= now:
        return None
    if entry.last_seen_at is None or now - entry.last_seen_at >= SEEN_RESOLUTION:
        entry.last_seen_at = now
    return entry.email


def revoke_session(session: Session, *, token: str, now: datetime) -> bool:
    entry = _find(session, TokenKind.SESSION, token)
    if entry is None or entry.used_at is not None:
        return False
    entry.used_at = now
    return True
