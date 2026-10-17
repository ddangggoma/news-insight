from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.auth import access, access_routes, accounts
from news_insight.auth.models import AccessKind, AccessLog, User, UserStatus

pytestmark = pytest.mark.db
PASSWORD = "plum-orbit-4417"
BROWSER = {"X-Client-IP": "203.0.113.7", "X-Client-UA": "Firefox"}
NOW = datetime.now(UTC)


@pytest.fixture
def boss(db_session: Session) -> User:
    return accounts.create_admin(
        db_session, username="boss", password=PASSWORD, name="관리자", now=NOW
    )


@pytest.fixture
def reader(db_session: Session) -> User:
    user = accounts.register(
        db_session,
        username="reader.one",
        password=PASSWORD,
        name="김독자",
        now=NOW,
        client=accounts.Client(),
    )
    user.status = UserStatus.ACTIVE
    db_session.flush()
    return user


@pytest.fixture
def client(console_client: TestClient, headers: dict[str, str]) -> Iterator[Any]:
    class Calls:
        def post(self, path: str, body: Any = None, **extra: str) -> Any:
            return console_client.post(path, json=body, headers={**headers, **BROWSER, **extra})

        def get(self, url: str, token: str, /, **params: Any) -> Any:
            return console_client.get(
                url, params=params, headers={**headers, "X-Session-Token": token}
            )

        def login(self, username: str, password: str = PASSWORD) -> str:
            response = self.post(
                "/api/admin/accounts/login", {"username": username, "password": password}
            )
            return str(response.json().get("token", ""))

    yield Calls()


def entry(user: User, path: str, *, at: datetime = NOW, **extra: Any) -> dict[str, Any]:
    return {
        "at": at.isoformat(),
        "user_id": user.id,
        "kind": "page",
        "method": "GET",
        "path": path,
        "ip": "203.0.113.7",
        **extra,
    }


def test_batch_is_stored_with_bad_times_and_gone_accounts_tidied(
    client: Any, db_session: Session, reader: User
) -> None:
    batch = [
        entry(reader, "/radar", query="period=week"),
        entry(reader, "/console", at=NOW + timedelta(hours=2)),  # clock skew: stamped on arrival
        entry(reader, "/" + "x" * 400, kind="api"),
        {**entry(reader, "/"), "user_id": reader.id + 999},  # account removed since
    ]

    response = client.post("/api/admin/access-log", {"entries": batch})

    assert response.status_code == 200 and response.json() == {"recorded": 3}
    rows = db_session.scalars(select(AccessLog).order_by(AccessLog.id)).all()
    assert [r.path[:7] for r in rows] == ["/radar", "/consol", "/xxxxxx"]
    assert rows[0].query == "period=week" and rows[0].ip == "203.0.113.7"
    assert rows[1].at <= datetime.now(UTC) and rows[1].at > NOW
    assert len(rows[2].path) == 300 and rows[2].kind == AccessKind.API


def test_batch_needs_the_console_key_and_caps_its_size(
    console_client: TestClient, client: Any, reader: User
) -> None:
    assert console_client.post("/api/admin/access-log", json={"entries": []}).status_code == 401
    too_many = [entry(reader, "/")] * (access_routes.BATCH_MAX + 1)
    assert client.post("/api/admin/access-log", {"entries": too_many}).status_code == 422


def test_requests_filter_by_account_address_kind_path_and_day(
    client: Any, db_session: Session, boss: User, reader: User
) -> None:
    yesterday = NOW - timedelta(days=1)
    old = access.Entry(yesterday, reader.id, AccessKind.PAGE, "GET", "/radar", ip="203.0.113.7")
    access.record(db_session, [old], now=yesterday)
    client.post(
        "/api/admin/access-log",
        {
            "entries": [
                entry(reader, "/radar/week", ip="198.51.100.4"),
                entry(reader, "/briefing", kind="action", method="post"),
                entry(boss, "/console/users"),
            ]
        },
    )
    token = client.login("boss")
    url = "/api/admin/access-log/requests"

    everything = client.get(url, token).json()
    mine = client.get(url, token, user=reader.id, path="/radar", size=1).json()
    by_ip = client.get(url, token, ip="198.51.").json()
    actions = client.get(url, token, kind="action").json()
    today = NOW.astimezone(ZoneInfo("Asia/Seoul")).date()
    on_day = client.get(url, token, user=reader.id, since=today, until=today).json()

    assert everything["total"] == 4
    assert everything["items"][-1]["path"] == "/radar"  # newest first
    assert mine["total"] == 2 and [i["path"] for i in mine["items"]] == ["/radar/week"]
    assert mine["items"][0]["user"] == {
        "id": reader.id,
        "username": "reader.one",
        "name": "김독자",
        "role": "reader",
    }
    assert [i["path"] for i in by_ip["items"]] == ["/radar/week"]
    assert [(i["path"], i["method"]) for i in actions["items"]] == [("/briefing", "POST")]
    assert {i["path"] for i in on_day["items"]} == {"/radar/week", "/briefing"}


def test_logins_list_successes_failures_and_logouts_with_the_address(
    client: Any, boss: User, reader: User
) -> None:
    token = client.login("reader.one")
    client.login("reader.one", "wrong-password-1")
    client.login("nobody.here", "wrong-password-1")
    client.post("/api/admin/accounts/logout", {"token": token})
    admin = client.login("boss")
    url = "/api/admin/access-log/logins"

    all_events = client.get(url, admin).json()
    failures = client.get(url, admin, outcome="fail").json()
    readers = client.get(url, admin, user=reader.id).json()

    assert [e["event"] for e in all_events["items"]] == [
        "login_ok",
        "logout",
        "login_fail",
        "login_fail",
        "login_ok",
    ]
    assert {e["ip"] for e in all_events["items"]} == {"203.0.113.7"}
    assert all_events["items"][0]["user_agent"] == "Firefox"
    assert [e["user"] and e["user"]["username"] for e in failures["items"]] == [None, "reader.one"]
    assert readers["total"] == 3


def test_usage_sums_each_account_and_the_most_used_paths(
    client: Any, boss: User, reader: User
) -> None:
    client.login("reader.one")
    client.login("reader.one", "wrong-password-1")
    client.post(
        "/api/admin/access-log",
        {
            "entries": [
                entry(reader, "/radar", at=NOW - timedelta(minutes=3), ip="198.51.100.4"),
                entry(reader, "/radar", at=NOW - timedelta(minutes=2)),
                entry(reader, "/briefing", kind="action", method="POST"),
            ]
        },
    )
    admin = client.login("boss")

    report = client.get("/api/admin/access-log/usage", admin).json()
    only_reader = client.get("/api/admin/access-log/usage", admin, user=reader.id).json()

    rows = {row["user"]["username"]: row for row in report["accounts"]}
    assert rows["reader.one"] | {"last_at": None} == {
        "user": rows["reader.one"]["user"],
        "requests": 3,
        "pages": 2,
        "actions": 1,
        "ips": 2,
        "last_at": None,
        "last_ip": "203.0.113.7",
        "logins": 1,
        "failures": 1,
    }
    assert rows["boss"]["requests"] == 0 and rows["boss"]["logins"] == 1
    assert report["paths"][0] == {
        "path": "/radar",
        "kind": "page",
        "count": 2,
        "last_at": report["paths"][0]["last_at"],
    }
    assert report["keep_days"] == 30
    assert [row["user"]["username"] for row in only_reader["accounts"]] == ["reader.one"]


def test_reads_are_for_admins_only(client: Any, boss: User, reader: User) -> None:
    token = client.login("reader.one")
    for path in ("requests", "logins", "usage"):
        assert client.get(f"/api/admin/access-log/{path}", token).status_code == 403
        assert client.get(f"/api/admin/access-log/{path}", "").status_code == 401


def test_purge_drops_access_rows_past_retention(db_session: Session, reader: User) -> None:
    old = NOW - access.ACCESS_KEEP - timedelta(hours=1)
    access.record(
        db_session,
        [
            access.Entry(at=NOW, user_id=reader.id, kind=AccessKind.PAGE, method="GET", path="/"),
            access.Entry(
                at=NOW, user_id=reader.id, kind=AccessKind.PAGE, method="GET", path="/old"
            ),
        ],
        now=NOW,
    )
    db_session.flush()
    db_session.execute(update(AccessLog).where(AccessLog.path == "/old").values(at=old))

    accounts.purge(db_session, now=NOW)

    assert db_session.scalars(select(AccessLog.path)).all() == ["/"]
