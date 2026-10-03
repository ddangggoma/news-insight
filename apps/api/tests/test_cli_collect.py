from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.collect.models import DeadLetter
from news_insight.sources.enums import SourceStatus, ValidationStage
from news_insight.sources.models import Source
from tests.factories import build_source
from tests.helpers import serving
from tests.parsers.test_feed_probe import item, rss

pytestmark = pytest.mark.db
runner = CliRunner()


class AllowAll:
    def try_acquire(self, domain: str, *, per_minute: int | None = None) -> bool:
        return True


@pytest.fixture(autouse=True)
def wire_cli(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session
        db_session.flush()

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(cli, "_fetcher", lambda: serving(rss(item(1), item(2), item(3))))
    monkeypatch.setattr(cli, "_limiter", AllowAll)


def add_source(session: Session, **overrides: Any) -> Source:
    source = build_source(**{"validation_stage": ValidationStage.V3, **overrides})
    session.add(source)
    session.flush()
    return source


def invoke(*args: str) -> Any:
    return runner.invoke(cli.app, list(args))


def test_collect_run_reports_the_outcome(db_session: Session) -> None:
    add_source(db_session)

    result = invoke("collect", "run", "example-news")

    assert result.exit_code == 0, result.output
    assert "example-news: success http=200 new=3 updated=0 unchanged=0" in result.output


def test_collect_status_lists_the_schedule(db_session: Session) -> None:
    add_source(db_session)
    invoke("collect", "run", "example-news")

    result = invoke("collect", "status")

    assert result.exit_code == 0, result.output
    assert "example-news" in result.output and "every=15m" in result.output


def test_dlq_list_and_dismiss(db_session: Session) -> None:
    source = add_source(db_session)
    letter = DeadLetter(source_id=source.id, error_code="timeout", error_message="t", attempts=4)
    db_session.add(letter)
    db_session.flush()

    listed = invoke("dlq", "list")
    dismissed = invoke("dlq", "dismiss", str(letter.id))

    assert f"#{letter.id} example-news timeout attempts=4" in listed.output
    assert dismissed.exit_code == 0 and "dismissed" in dismissed.output


def test_dlq_retry_requires_a_resumed_source(db_session: Session) -> None:
    source = add_source(db_session, status=SourceStatus.PAUSED, paused_reason="selector_drift")
    letter = DeadLetter(
        source_id=source.id, error_code="selector_drift", error_message="x", attempts=1
    )
    db_session.add(letter)
    db_session.flush()

    blocked = invoke("dlq", "retry", str(letter.id))
    invoke("sources", "resume", "example-news")
    retried = invoke("dlq", "retry", str(letter.id))

    assert blocked.exit_code == 2 and "resume it first" in blocked.output
    assert retried.exit_code == 0 and "retried" in retried.output


def test_sources_canary_reports_when_nothing_is_ready(db_session: Session) -> None:
    add_source(db_session)

    result = invoke("sources", "canary")

    assert result.exit_code == 0
    assert "no sources ready for V4 yet" in result.output


def test_sources_pause_and_resume(db_session: Session) -> None:
    source = add_source(db_session)

    paused = invoke("sources", "pause", "example-news", "--reason", "maintenance")
    status_while_paused = source.status
    resumed = invoke("sources", "resume", "example-news")

    assert paused.exit_code == 0 and "paused (maintenance)" in paused.output
    assert status_while_paused is SourceStatus.PAUSED
    assert resumed.exit_code == 0 and source.status is SourceStatus.CANDIDATE
