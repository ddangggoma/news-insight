from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.digest.claude import ClaudeError, ClaudeResult
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.spotlight.models import Spotlight, SpotlightFreeze, SpotlightStatus
from tests.sources.test_catalog import ENTRY, write_catalog

pytestmark = pytest.mark.db
runner = CliRunner()


@pytest.fixture(autouse=True)
def wire_cli(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session
        db_session.flush()

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("CLI tests must not reach the network")

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(
        cli,
        "_fetcher",
        lambda: SafeFetcher(
            client=httpx.Client(transport=httpx.MockTransport(no_network)),
            resolver=lambda host, port: ["93.184.216.34"],
            verify_peer=False,
        ),
    )


def seed(tmp_path: Path, body: str = ENTRY) -> None:
    result = runner.invoke(
        cli.app, ["sources", "seed", "--catalog", str(write_catalog(tmp_path, body))]
    )
    assert result.exit_code == 0, result.output


def test_seed_reports_created_sources(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app, ["sources", "seed", "--catalog", str(write_catalog(tmp_path, ENTRY))]
    )

    assert result.exit_code == 0, result.output
    assert "created=1 updated=0 reset=0" in result.output


def test_validate_stops_at_policy_failure_with_exit_code_1(tmp_path: Path) -> None:
    seed(tmp_path, ENTRY.replace("terms_url: https://", "terms_url: http://"))

    result = runner.invoke(cli.app, ["sources", "validate", "example-news"])

    assert result.exit_code == 1
    assert "V0 passed: ok" in result.output
    assert "V1 failed: terms_url must use https" in result.output
    assert "example-news: stage=V0 status=candidate" in result.output


def test_validate_rejects_targets_beyond_v3() -> None:
    result = runner.invoke(cli.app, ["sources", "validate", "example-news", "--until", "V6"])

    assert result.exit_code == 2
    assert "use 'promote' for V6" in result.output


def test_validate_unknown_source_exits_2() -> None:
    result = runner.invoke(cli.app, ["sources", "validate", "nope"])

    assert result.exit_code == 2
    assert "unknown source 'nope'" in result.output


def test_promote_requires_v5(tmp_path: Path) -> None:
    seed(tmp_path)

    result = runner.invoke(cli.app, ["sources", "promote", "example-news"])

    assert result.exit_code == 2
    assert "next stage is V0, not V6" in result.output


def test_report_lists_tracks_regions_and_stages(tmp_path: Path) -> None:
    seed(tmp_path)

    result = runner.invoke(cli.app, ["sources", "report"])

    assert result.exit_code == 0, result.output
    assert "news" in result.output and "0/100" in result.output
    assert "greater_china" in result.output and "0/21" in result.output
    assert "unverified" in result.output


def test_ops_keys_reports_missing_keys_without_values(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_insight.config import Settings

    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.delenv("SOURCE_SECRET_EPO_OPS_KEY", raising=False)
    result = CliRunner().invoke(cli.app, ["ops", "keys"])
    assert result.exit_code == 0
    assert "OPENALEX_API_KEY is not set" in result.output
    assert "SOURCE_SECRET_EPO_OPS_KEY is not configured" in result.output


SPOTLIGHT_DAY = date(2026, 11, 3)
SPOTLIGHT_AT = datetime(2026, 11, 2, 20, 30, tzinfo=UTC)  # 05:30 KST on SPOTLIGHT_DAY


def clock_at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    class Frozen(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "Frozen":  # type: ignore[override]
            return cls.fromtimestamp(moment.timestamp(), tz)

    monkeypatch.setattr(cli, "datetime", Frozen)


class FailingClaude:
    def generate(self, payload: dict[str, Any], **kwargs: Any) -> ClaudeResult:
        raise ClaudeError("claude login expired")


def test_spotlight_write_noop_when_published(db_session: Session) -> None:
    freeze = SpotlightFreeze(spotlight_date=SPOTLIGHT_DAY, frozen_at=SPOTLIGHT_AT, candidates={})
    db_session.add(freeze)
    db_session.flush()
    db_session.add(
        Spotlight(
            spotlight_date=SPOTLIGHT_DAY,
            status=SpotlightStatus.PUBLISHED,
            model="claude-opus-5-5",
            headline="",
            benchmark_note="",
            freeze_id=freeze.id,
            generated_at=SPOTLIGHT_AT,
        )
    )
    db_session.flush()

    result = runner.invoke(cli.app, ["spotlight", "write", "--date", "2026-11-03"])

    assert result.exit_code == 0, result.output
    assert "2026-11-03 spotlight already published; nothing to do" in result.output


def test_spotlight_write_commits_the_failed_row_before_exiting_1(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def real_scope() -> Iterator[Session]:
        """Like db.session_scope: commit on success, roll back when anything propagates."""
        try:
            yield db_session
        except BaseException:
            db_session.rollback()
            raise
        db_session.commit()

    monkeypatch.setattr(cli, "session_scope", real_scope)
    monkeypatch.setattr(cli, "_spotlight_claude", lambda: FailingClaude())
    clock_at(monkeypatch, SPOTLIGHT_AT)  # 05:30 KST: not the last attempt

    result = runner.invoke(cli.app, ["spotlight", "write", "--date", "2026-11-03"])

    assert result.exit_code == 1
    assert "claude login expired" in result.output
    row = db_session.scalars(
        select(Spotlight).where(Spotlight.spotlight_date == SPOTLIGHT_DAY)
    ).one()
    assert row.status is SpotlightStatus.FAILED and row.error == "claude login expired"
    # the on-the-spot freeze survived with it
    assert db_session.scalars(select(SpotlightFreeze)).one().spotlight_date == SPOTLIGHT_DAY


def test_spotlight_write_from_ten_publishes_the_fallback(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_spotlight_claude", lambda: FailingClaude())
    clock_at(monkeypatch, datetime(2026, 11, 3, 1, 0, tzinfo=UTC))  # 10:00 KST

    result = runner.invoke(cli.app, ["spotlight", "write", "--date", "2026-11-03"])

    assert result.exit_code == 0, result.output
    row = db_session.scalars(
        select(Spotlight).where(Spotlight.spotlight_date == SPOTLIGHT_DAY)
    ).one()
    assert row.status is SpotlightStatus.PUBLISHED
    assert "fallback: claude login expired" in result.output


def test_spotlight_freeze_is_idempotent() -> None:
    first = runner.invoke(cli.app, ["spotlight", "freeze", "--date", "2026-11-03"])
    second = runner.invoke(cli.app, ["spotlight", "freeze", "--date", "2026-11-03"])

    assert first.exit_code == second.exit_code == 0, first.output + second.output
    assert first.output == second.output and "2026-11-03 frozen" in first.output
