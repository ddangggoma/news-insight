from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.auth import account_routes, accounts
from news_insight.auth.models import AuthEvent, User

pytestmark = pytest.mark.db
PASSWORD = "plum-orbit-4417"
BROWSER = {"X-Client-IP": "203.0.113.7", "X-Client-UA": "Firefox"}
runner = CliRunner()


@pytest.fixture
def api(console_client: TestClient, headers: dict[str, str]) -> Iterator[Any]:
    def post(path: str, body: dict[str, Any] | None = None, **extra: str) -> Any:
        return console_client.post(path, json=body, headers={**headers, **BROWSER, **extra})

    yield post


@pytest.fixture
def boss(db_session: Session) -> User:
    return accounts.create_admin(
        db_session, username="boss", password=PASSWORD, name="관리자", now=datetime.now(UTC)
    )


def session_token(api: Any, username: str = "boss") -> str:
    response = api("/api/admin/accounts/login", {"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


def test_signup_login_approval_flow(
    api: Any,
    boss: User,
    console_client: TestClient,
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mails: list[dict[str, Any]] = []
    monkeypatch.setattr(
        account_routes.mailer, "send_email", lambda settings, **kw: mails.append(kw) or True
    )

    created = api(
        "/api/admin/accounts/signup",
        {"username": "Reader.One", "password": PASSWORD, "name": "김독자"},
    )
    assert created.status_code == 201 and created.json() == {"status": "pending"}
    assert mails and mails[0]["subject"].endswith("김독자 (reader.one)")
    assert "/console/users" in mails[0]["body"]

    pending = api("/api/admin/accounts/login", {"username": "reader.one", "password": PASSWORD})
    assert pending.status_code == 403 and pending.json() == {"outcome": "pending"}
    wrong = api("/api/admin/accounts/login", {"username": "reader.one", "password": "nope-nope"})
    assert wrong.status_code == 401 and wrong.json() == {"outcome": "invalid"}

    admin_token = session_token(api)
    admin_headers = {**headers, "X-Session-Token": admin_token}
    listed = console_client.get(
        "/api/admin/users", params={"status": "pending"}, headers=admin_headers
    )
    assert listed.status_code == 200
    body = listed.json()
    assert [u["username"] for u in body["items"]] == ["reader.one"] and body["counts"][
        "pending"
    ] == 1
    reader_id = body["items"][0]["id"]

    approved = api(f"/api/admin/users/{reader_id}/approve", **{"X-Session-Token": admin_token})
    assert approved.status_code == 200 and approved.json()["status"] == "active"

    token = session_token(api, "reader.one")
    me = api("/api/admin/accounts/session", {"token": token})
    assert me.json()["username"] == "reader.one" and me.json()["role"] == "reader"
    assert "password_hash" not in me.json()

    # a reader's session cannot reach the admin routes
    denied = console_client.get("/api/admin/users", headers={**headers, "X-Session-Token": token})
    assert denied.status_code == 403
    assert console_client.get("/api/admin/users", headers=headers).status_code == 401

    api("/api/admin/accounts/logout", {"token": token})
    assert api("/api/admin/accounts/session", {"token": token}).status_code == 401


def test_signup_errors_name_the_field(api: Any) -> None:
    taken = {"username": "dup.user", "password": PASSWORD, "name": "한 명"}
    assert api("/api/admin/accounts/signup", taken).status_code == 201
    again = api("/api/admin/accounts/signup", taken)
    weak = api(
        "/api/admin/accounts/signup", {"username": "weak.user", "password": "x", "name": "약함"}
    )

    assert again.status_code == 400 and again.json()["detail"]["field"] == "username"
    assert weak.status_code == 400 and weak.json()["detail"]["field"] == "password"


def test_routes_need_the_console_key(console_client: TestClient) -> None:
    response = console_client.post(
        "/api/admin/accounts/login", json={"username": "boss", "password": PASSWORD}
    )
    assert response.status_code == 401


def test_password_change_returns_a_new_session_and_ends_the_old_ones(api: Any, boss: User) -> None:
    old = session_token(api)
    other = session_token(api)

    bad = api(
        "/api/admin/accounts/password",
        {"token": old, "current": "wrong-current", "password": "quiet-harbor-9921"},
    )
    assert bad.status_code == 400 and bad.json()["detail"]["field"] == "current"
    changed = api(
        "/api/admin/accounts/password",
        {"token": old, "current": PASSWORD, "password": "quiet-harbor-9921"},
    )
    assert changed.status_code == 200
    fresh = changed.json()["token"]
    assert api("/api/admin/accounts/session", {"token": fresh}).status_code == 200
    for token in (old, other):
        assert api("/api/admin/accounts/session", {"token": token}).status_code == 401


def test_logout_others_keeps_the_current_session(api: Any, boss: User) -> None:
    current, other = session_token(api), session_token(api)

    assert api("/api/admin/accounts/logout-others", {"token": current}).status_code == 204
    assert api("/api/admin/accounts/session", {"token": current}).status_code == 200
    assert api("/api/admin/accounts/session", {"token": other}).status_code == 401


def test_admin_actions_role_reset_and_conflicts(
    api: Any, boss: User, db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    api(
        "/api/admin/accounts/signup", {"username": "reader.two", "password": PASSWORD, "name": "둘"}
    )
    reader = accounts.find_user(db_session, "reader.two")
    assert reader is not None
    admin = {"X-Session-Token": session_token(api)}

    assert api(f"/api/admin/users/{reader.id}/suspend", **admin).status_code == 409
    assert api(f"/api/admin/users/{boss.id}/suspend", **admin).status_code == 409
    assert api(f"/api/admin/users/{reader.id}/approve", **admin).status_code == 200
    promoted = api(f"/api/admin/users/{reader.id}/role", {"role": "admin"}, **admin)
    assert promoted.status_code == 200 and promoted.json()["role"] == "admin"

    reset = api(f"/api/admin/users/{reader.id}/reset-password", **admin)
    temporary = reset.json()["temporary_password"]
    login = api("/api/admin/accounts/login", {"username": "reader.two", "password": temporary})
    assert login.json()["user"]["must_change_password"] is True
    # an admin with a temporary password must change it before acting
    forced = console_client.get(
        "/api/admin/users", headers={**headers, "X-Session-Token": login.json()["token"]}
    )
    assert forced.status_code == 403

    trail = console_client.get(f"/api/admin/users/{reader.id}/events", headers={**headers, **admin})
    assert [e["event"] for e in trail.json()][:3] == ["login_ok", "password_reset", "role_admin"]
    assert trail.json()[0]["ip"] == "203.0.113.7"
    unknown = api("/api/admin/users/999999/explode", **admin)
    assert unknown.status_code == 422


def test_cli_creates_an_admin_from_stdin_and_recovers_accounts(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session
        db_session.flush()

    monkeypatch.setattr(cli, "session_scope", scope)

    created = runner.invoke(
        cli.app,
        ["users", "create-admin", "owner", "--name", "운영자", "--password-stdin"],
        input=f"{PASSWORD}\n",
    )
    assert created.exit_code == 0, created.output
    weak = runner.invoke(
        cli.app,
        ["users", "create-admin", "owner2", "--name", "둘", "--password-stdin"],
        input="short\n",
    )
    assert weak.exit_code == 2 and "10자" in weak.output

    accounts.register(
        db_session,
        username="waiting",
        password=PASSWORD,
        name="대기",
        now=datetime.now(UTC),
        client=accounts.Client(),
    )
    assert runner.invoke(cli.app, ["users", "approve", "waiting"]).exit_code == 0
    listed = runner.invoke(cli.app, ["users", "list"])
    assert "owner" in listed.output and "waiting" in listed.output and "active" in listed.output

    reset = runner.invoke(cli.app, ["users", "reset-password", "waiting"])
    temporary = reset.output.strip()
    assert reset.exit_code == 0 and len(temporary) >= 16
    assert runner.invoke(cli.app, ["users", "unlock", "waiting"]).exit_code == 0
    assert runner.invoke(cli.app, ["users", "unlock", "nobody"]).exit_code == 2

    actors = db_session.scalars(
        select(AuthEvent.actor_id).where(AuthEvent.event == "approve")
    ).all()
    assert actors == [None]  # the host CLI acts without an admin account
