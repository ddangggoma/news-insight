from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.auth import mailer, service
from news_insight.auth.models import AdminToken, TokenKind
from news_insight.config import Settings

pytestmark = pytest.mark.db
ADMIN = "ddangggoma@gmail.com"
NOW = datetime(2026, 10, 5, 1, 0, tzinfo=UTC)


def test_only_the_admin_address_gets_a_link(db_session: Session) -> None:
    assert (
        service.issue_login(db_session, email="else@example.com", admin_email=ADMIN, now=NOW)
        is None
    )
    issued = service.issue_login(
        db_session, email="  DdangGGoma@Gmail.com ", admin_email=ADMIN, now=NOW
    )

    assert issued is not None
    stored = db_session.scalars(select(AdminToken)).one()
    assert stored.token_hash == service.hash_token(issued.token)
    assert issued.token not in stored.token_hash  # only the hash is stored
    assert stored.expires_at == NOW + service.LOGIN_TTL


def test_links_are_single_use_and_expire(db_session: Session) -> None:
    first = service.issue_login(db_session, email=ADMIN, admin_email=ADMIN, now=NOW)
    late = service.issue_login(db_session, email=ADMIN, admin_email=ADMIN, now=NOW)
    assert first is not None and late is not None

    opened = service.consume_login(db_session, token=first.token, now=NOW + timedelta(minutes=1))
    replay = service.consume_login(db_session, token=first.token, now=NOW + timedelta(minutes=2))
    expired = service.consume_login(db_session, token=late.token, now=NOW + timedelta(minutes=16))

    assert opened is not None and replay is None and expired is None
    assert service.check_session(db_session, token=opened.token, now=NOW) == ADMIN
    assert service.check_session(db_session, token="forged", now=NOW) is None
    assert service.check_session(db_session, token=first.token, now=NOW) is None  # wrong kind


def test_sessions_expire_and_can_be_revoked(db_session: Session) -> None:
    link = service.issue_login(db_session, email=ADMIN, admin_email=ADMIN, now=NOW)
    assert link is not None
    session = service.consume_login(db_session, token=link.token, now=NOW)
    assert session is not None

    assert (
        service.check_session(db_session, token=session.token, now=NOW + timedelta(days=15)) is None
    )
    assert service.revoke_session(db_session, token=session.token, now=NOW) is True
    assert service.check_session(db_session, token=session.token, now=NOW) is None


def test_link_requests_are_rate_limited(db_session: Session) -> None:
    issued = [
        service.issue_login(
            db_session, email=ADMIN, admin_email=ADMIN, now=NOW + timedelta(seconds=i)
        )
        for i in range(service.RATE_LIMIT + 1)
    ]

    assert all(issued[: service.RATE_LIMIT]) and issued[-1] is None
    later = NOW + service.RATE_WINDOW + timedelta(seconds=10)
    assert service.issue_login(db_session, email=ADMIN, admin_email=ADMIN, now=later) is not None


def test_login_url_and_message() -> None:
    settings = Settings(_env_file=None, public_base_url="https://news.example/", smtp_user="bot@x")
    url = mailer.login_url(settings, "abc")
    message = mailer.build_message(settings, to=ADMIN, url=url)

    assert url == "https://news.example/login/verify?token=abc"
    assert message["To"] == ADMIN and url in message.get_content()
    assert mailer.send_login_link(Settings(_env_file=None), to=ADMIN, url=url) is False


def test_auth_api_flow(
    console_client: TestClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(mailer, "send_login_link", lambda settings, **kw: sent.append(kw) or True)

    stranger = console_client.post(
        "/api/admin/auth/request", json={"email": "x@y.z"}, headers=headers
    )
    admin = console_client.post("/api/admin/auth/request", json={"email": ADMIN}, headers=headers)
    assert stranger.status_code == admin.status_code == 202
    assert len(sent) == 1 and sent[0]["to"] == ADMIN

    token = sent[0]["url"].split("token=")[1]
    verified = console_client.post("/api/admin/auth/verify", json={"token": token}, headers=headers)
    assert verified.status_code == 200
    again = console_client.post("/api/admin/auth/verify", json={"token": token}, headers=headers)
    assert again.status_code == 401

    session = verified.json()["token"]
    who = console_client.post("/api/admin/auth/session", json={"token": session}, headers=headers)
    assert who.json() == {"email": ADMIN}
    console_client.post("/api/admin/auth/logout", json={"token": session}, headers=headers)
    gone = console_client.post("/api/admin/auth/session", json={"token": session}, headers=headers)
    assert gone.status_code == 401
    assert (
        console_client.post("/api/admin/auth/session", json={"token": session}).status_code == 401
    )


def test_tokens_kind_enum() -> None:
    assert {k.value for k in TokenKind} == {"login", "session"}
