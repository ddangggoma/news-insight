from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from news_insight.auth import accounts, passwords
from news_insight.auth.accounts import ActionError, Client, FormError, LoginOutcome, Throttled
from news_insight.auth.models import AuthEvent, Role, User, UserSession, UserStatus

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 7, 1, 0, tzinfo=UTC)
PASSWORD = "plum-orbit-4417"
WEB = Client(ip="203.0.113.7", user_agent="pytest")


def signup(session: Session, username: str = "reader.one", name: str = "김독자") -> User:
    return accounts.register(
        session, username=username, password=PASSWORD, name=name, now=NOW, client=WEB
    )


def admin(session: Session, username: str = "boss") -> User:
    return accounts.create_admin(
        session, username=username, password=PASSWORD, name="관리자", now=NOW
    )


def login(
    session: Session, username: str, password: str = PASSWORD, at: datetime = NOW
) -> accounts.Login:
    return accounts.authenticate(session, username=username, password=password, now=at, client=WEB)


def events(session: Session) -> list[str]:
    return list(session.scalars(select(AuthEvent.event).order_by(AuthEvent.id)))


def test_signup_stores_an_argon2id_hash_and_waits_for_approval(db_session: Session) -> None:
    user = signup(db_session, username="  Reader.One ")

    assert user.username == "reader.one" and user.name == "김독자"
    assert user.status == UserStatus.PENDING and user.role == Role.READER
    assert user.password_hash.startswith("$argon2id$")
    stored = db_session.execute(text("SELECT password_hash FROM users")).scalar_one()
    assert PASSWORD not in stored
    assert events(db_session) == ["signup"]


@pytest.mark.parametrize(
    ("username", "password", "name", "field"),
    [
        ("ab", PASSWORD, "이름", "username"),
        ("bad name", PASSWORD, "이름", "username"),
        ("한글아이디", PASSWORD, "이름", "username"),
        ("reader.two", "short", "이름", "password"),
        ("reader.two", "aaaaaaaaaaaa", "이름", "password"),
        ("reader.two", "reader.two-2026!", "이름", "password"),
        ("reader.two", "1234567890", "이름", "password"),
        ("reader.two", PASSWORD, "   ", "name"),
        ("reader.two", PASSWORD, "x" * 51, "name"),
        ("reader.two", PASSWORD, "tab\there", "name"),
    ],
)
def test_signup_rejects_bad_input(
    db_session: Session, username: str, password: str, name: str, field: str
) -> None:
    with pytest.raises(FormError) as error:
        accounts.register(
            db_session, username=username, password=password, name=name, now=NOW, client=WEB
        )
    assert error.value.field == field


def test_signup_refuses_a_taken_username(db_session: Session) -> None:
    signup(db_session)
    with pytest.raises(FormError) as error:
        signup(db_session, username="READER.ONE")
    assert error.value.field == "username"


def test_signups_are_limited_per_address_and_by_the_pending_cap(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(accounts, "SIGNUP_LIMIT", 2)
    signup(db_session, username="first")
    signup(db_session, username="second")
    with pytest.raises(Throttled):
        signup(db_session, username="third")
    other = Client(ip="198.51.100.9")
    monkeypatch.setattr(accounts, "PENDING_CAP", 2)
    with pytest.raises(FormError) as error:
        accounts.register(
            db_session, username="fourth", password=PASSWORD, name="넷", now=NOW, client=other
        )
    assert error.value.field is None


def test_only_approved_accounts_log_in(db_session: Session) -> None:
    boss = admin(db_session)
    user = signup(db_session)

    pending = login(db_session, "reader.one")
    assert pending.outcome == LoginOutcome.PENDING

    accounts.approve(db_session, boss, user.id, now=NOW, client=WEB)
    approved = login(db_session, "reader.one")
    assert approved.outcome == LoginOutcome.OK and approved.user is not None
    assert user.reviewed_by == boss.id and user.last_login_at == NOW


def test_a_wrong_password_never_reveals_the_account_state(db_session: Session) -> None:
    boss = admin(db_session)
    pending = signup(db_session, username="waiting")
    rejected = signup(db_session, username="refused")
    accounts.reject(db_session, boss, rejected.id, now=NOW, client=WEB)

    assert pending.status == UserStatus.PENDING
    for username in ("waiting", "refused", "nobody-here", "boss"):
        assert login(db_session, username, "not-the-password").outcome == LoginOutcome.INVALID
    assert login(db_session, "refused").outcome == LoginOutcome.REJECTED


def test_unknown_usernames_still_spend_a_verification(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    burned: list[str] = []
    monkeypatch.setattr(passwords, "burn_time", burned.append)

    assert login(db_session, "ghost").outcome == LoginOutcome.INVALID
    assert burned == [PASSWORD]


def test_five_failures_lock_the_account_and_the_lock_grows(db_session: Session) -> None:
    admin(db_session)
    for _ in range(accounts.LOCK_AFTER):
        assert login(db_session, "boss", "wrong-password").outcome == LoginOutcome.INVALID
    user = accounts.find_user(db_session, "boss")
    assert user is not None and user.locked_until == NOW + accounts.LOCK_BASE

    # locked: the right password answers like a wrong one
    assert login(db_session, "boss").outcome == LoginOutcome.INVALID
    later = NOW + accounts.LOCK_BASE + timedelta(seconds=1)
    assert login(db_session, "boss", "wrong-again", at=later).outcome == LoginOutcome.INVALID
    assert user.locked_until == later + accounts.LOCK_BASE * 2

    accounts.unlock(db_session, None, user.id, now=later)
    assert login(db_session, "boss", at=later).outcome == LoginOutcome.OK
    assert user.failed_count == 0
    assert "locked" in events(db_session) and "login_locked" in events(db_session)


def test_failed_logins_are_throttled_per_address(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(accounts, "IP_FAIL_LIMIT", 3)
    admin(db_session)
    for _ in range(3):
        login(db_session, "nobody", "x")
    assert login(db_session, "boss").outcome == LoginOutcome.THROTTLED
    other = accounts.authenticate(
        db_session, username="boss", password=PASSWORD, now=NOW, client=Client(ip="198.51.100.1")
    )
    assert other.outcome == LoginOutcome.OK


def test_sessions_hash_tokens_and_expire(db_session: Session) -> None:
    boss = admin(db_session)
    issued = accounts.issue_session(db_session, boss, now=NOW, client=WEB)

    stored = db_session.scalars(select(UserSession)).one()
    assert stored.token_hash == accounts.hash_token(issued.token) != issued.token
    assert accounts.check_session(db_session, token=issued.token, now=NOW) is boss
    assert accounts.check_session(db_session, token="forged", now=NOW) is None
    idle = NOW + accounts.IDLE_TTL + timedelta(seconds=1)
    assert accounts.check_session(db_session, token=issued.token, now=idle) is None

    fresh = accounts.issue_session(db_session, boss, now=NOW, client=WEB)
    for day in range(1, 14):
        assert (
            accounts.check_session(db_session, token=fresh.token, now=NOW + timedelta(days=day))
            is boss
        )
    assert (
        accounts.check_session(db_session, token=fresh.token, now=NOW + accounts.SESSION_TTL)
        is None
    )


def test_sessions_end_on_logout_suspension_role_change_and_password_change(
    db_session: Session,
) -> None:
    boss = admin(db_session)
    user = signup(db_session)
    accounts.approve(db_session, boss, user.id, now=NOW, client=WEB)

    def live() -> str:
        return accounts.issue_session(db_session, user, now=NOW, client=WEB).token

    token = live()
    assert accounts.revoke_session(db_session, token=token, now=NOW) == user.id
    assert accounts.check_session(db_session, token=token, now=NOW) is None

    token = live()
    accounts.set_role(db_session, boss, user.id, Role.ADMIN, now=NOW, client=WEB)
    assert accounts.check_session(db_session, token=token, now=NOW) is None

    token = live()
    accounts.suspend(db_session, boss, user.id, now=NOW, client=WEB)
    assert accounts.check_session(db_session, token=token, now=NOW) is None
    accounts.reactivate(db_session, boss, user.id, now=NOW, client=WEB)

    kept, other = live(), live()
    accounts.revoke_all(db_session, user.id, now=NOW, keep=kept)
    assert accounts.check_session(db_session, token=kept, now=NOW) is user
    assert accounts.check_session(db_session, token=other, now=NOW) is None

    accounts.change_password(
        db_session, user, current=PASSWORD, new="quiet-harbor-9921", now=NOW, client=WEB
    )
    assert accounts.check_session(db_session, token=kept, now=NOW) is None
    assert login(db_session, "reader.one", "quiet-harbor-9921").outcome == LoginOutcome.OK


def test_password_change_checks_the_current_password_and_policy(db_session: Session) -> None:
    boss = admin(db_session)
    for current, new, field in (
        ("wrong-current-pw", "quiet-harbor-9921", "current"),
        (PASSWORD, PASSWORD, "password"),
        (PASSWORD, "short", "password"),
    ):
        with pytest.raises(FormError) as error:
            accounts.change_password(
                db_session, boss, current=current, new=new, now=NOW, client=WEB
            )
        assert error.value.field == field


def test_reset_password_forces_a_change_and_unlocks(db_session: Session) -> None:
    boss = admin(db_session)
    user = signup(db_session)
    accounts.approve(db_session, boss, user.id, now=NOW, client=WEB)
    for _ in range(accounts.LOCK_AFTER):
        login(db_session, "reader.one", "wrong-password")

    temporary = accounts.reset_password(db_session, boss, user.id, now=NOW, client=WEB)

    result = login(db_session, "reader.one", temporary)
    assert result.outcome == LoginOutcome.OK and user.must_change_password
    accounts.change_password(
        db_session, user, current=temporary, new="quiet-harbor-9921", now=NOW, client=WEB
    )
    assert not user.must_change_password


def test_admin_guards(db_session: Session) -> None:
    boss = admin(db_session)
    user = signup(db_session)

    with pytest.raises(ActionError):
        accounts.suspend(db_session, boss, boss.id, now=NOW, client=WEB)  # self
    with pytest.raises(ActionError):
        accounts.suspend(db_session, boss, user.id, now=NOW, client=WEB)  # still pending
    with pytest.raises(ActionError):
        accounts.suspend(db_session, None, boss.id, now=NOW, client=WEB)  # last admin
    with pytest.raises(ActionError):
        accounts.set_role(db_session, None, boss.id, Role.READER, now=NOW, client=WEB)

    second = admin(db_session, "deputy")
    accounts.set_role(db_session, second, boss.id, Role.READER, now=NOW, client=WEB)
    assert boss.role == Role.READER


def test_admin_actions_are_audited_with_the_actor(db_session: Session) -> None:
    boss = admin(db_session)
    user = signup(db_session)
    accounts.approve(db_session, boss, user.id, now=NOW, client=WEB)

    approval = db_session.scalars(select(AuthEvent).where(AuthEvent.event == "approve")).one()
    assert approval.user_id == user.id and approval.actor_id == boss.id
    assert [e.event for e in accounts.user_events(db_session, user.id)] == ["approve", "signup"]
    assert accounts.status_counts(db_session) == {
        "pending": 0,
        "active": 2,
        "rejected": 0,
        "suspended": 0,
    }


def test_purge_drops_dead_sessions_old_signups_and_old_audit_rows(db_session: Session) -> None:
    boss = admin(db_session)
    stale = signup(db_session, username="stale")
    refused = signup(db_session, username="refused")
    recent = signup(db_session, username="recent")
    accounts.reject(db_session, boss, refused.id, now=NOW, client=WEB)
    recent.created_at = NOW + accounts.PENDING_KEEP
    dead = accounts.issue_session(db_session, boss, now=NOW, client=WEB)
    accounts.revoke_session(db_session, token=dead.token, now=NOW)
    db_session.flush()

    later = NOW + accounts.PENDING_KEEP + timedelta(days=1)
    accounts.purge(db_session, now=later)

    remaining = set(db_session.scalars(select(User.username)))
    assert remaining == {"boss", "recent"}
    assert stale.status == UserStatus.PENDING
    assert db_session.scalars(select(UserSession)).all() == []
    accounts.purge(db_session, now=NOW + accounts.EVENTS_KEEP + timedelta(days=200))
    assert db_session.scalars(select(AuthEvent).where(AuthEvent.at < NOW)).all() == []
