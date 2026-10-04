from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base, str_enum


class TokenKind(StrEnum):
    LOGIN = "login"  # single-use magic link, short-lived
    SESSION = "session"  # browser session behind the httpOnly cookie


class AdminToken(Base):
    """Admin magic-link and session tokens. Only SHA-256 hashes are stored (§9)."""

    __tablename__ = "admin_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[TokenKind] = mapped_column(str_enum(TokenKind))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # login: when the link was consumed; session: when it was revoked (logout)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
