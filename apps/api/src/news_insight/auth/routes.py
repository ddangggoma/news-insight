"""Admin auth API, internal like the rest of /api/admin: only the web server calls it."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from news_insight.auth import mailer, service
from news_insight.config import Settings, get_settings
from news_insight.console.auth import require_console_key
from news_insight.db import get_db

router = APIRouter(
    prefix="/api/admin/auth", tags=["auth"], dependencies=[Depends(require_console_key)]
)
DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class TokenBody(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class Accepted(BaseModel):
    accepted: bool = True


class SessionOut(BaseModel):
    token: str
    expires_at: datetime


class Whoami(BaseModel):
    email: str


def _now() -> datetime:
    return datetime.now(UTC)


@router.post("/request", status_code=status.HTTP_202_ACCEPTED)
def request_link(body: LoginRequest, db: DB, settings: Config) -> Accepted:
    """Always 202, so the response never tells whether the address is the admin's."""
    issued = service.issue_login(db, email=body.email, admin_email=settings.admin_email, now=_now())
    if issued is not None:
        db.commit()
        mailer.send_login_link(
            settings, to=settings.admin_email, url=mailer.login_url(settings, issued.token)
        )
    return Accepted()


@router.post("/verify")
def verify(body: TokenBody, db: DB) -> SessionOut:
    issued = service.consume_login(db, token=body.token, now=_now())
    db.commit()
    if issued is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired link")
    return SessionOut(token=issued.token, expires_at=issued.expires_at)


@router.post("/session")
def whoami(body: TokenBody, db: DB) -> Whoami:
    email = service.check_session(db, token=body.token, now=_now())
    db.commit()
    if email is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no session")
    return Whoami(email=email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: TokenBody, db: DB) -> None:
    service.revoke_session(db, token=body.token, now=_now())
    db.commit()
