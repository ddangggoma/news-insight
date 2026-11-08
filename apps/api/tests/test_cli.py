from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.benchmarks.models import BenchmarkScore, BenchmarkSnapshot
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


class CapturingClaude:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def generate(self, payload: dict[str, Any], **kwargs: Any) -> ClaudeResult:
        self.payloads.append(payload)
        return ClaudeResult(
            structured={"headline": "", "benchmark_note": "", "sections": {}},
            model="claude-opus-5-5",
            cost_usd=0.1,
        )


def _leaderboard(db_session: Session, hours_ago: int, order: tuple[str, str]) -> None:
    snapshot = BenchmarkSnapshot(
        site="lmarena",
        release=str(hours_ago),
        fetched_at=SPOTLIGHT_AT - timedelta(hours=hours_ago),
        sha256=str(hours_ago),
        raw={},
    )
    db_session.add(snapshot)
    db_session.flush()
    for value, model in zip((1500.0, 1400.0), order, strict=True):
        db_session.add(
            BenchmarkScore(
                snapshot_id=snapshot.id,
                site="lmarena",
                board="text",
                model_raw=model,
                metric="rating",
                value=value,
                extra={},
            )
        )
    db_session.flush()


def test_spotlight_write_gives_opus_the_benchmark_moves(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _leaderboard(db_session, 28, ("alpha", "beta"))
    _leaderboard(db_session, 2, ("beta", "alpha"))
    claude = CapturingClaude()
    monkeypatch.setattr(cli, "_spotlight_claude", lambda: claude)
    clock_at(monkeypatch, SPOTLIGHT_AT)

    result = runner.invoke(cli.app, ["spotlight", "write", "--date", "2026-11-03"])

    assert result.exit_code == 0, result.output
    changes = claude.payloads[0]["benchmarks"]["changes"]
    assert {(c["model"], c["from"], c["to"]) for c in changes} == {("beta", 2, 1), ("alpha", 1, 2)}


def test_spotlight_write_goes_on_when_the_benchmark_view_breaks(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(session: Session, *, now: datetime) -> dict[str, Any]:
        raise RuntimeError("bad benchmark data")

    claude = CapturingClaude()
    monkeypatch.setattr(cli, "_spotlight_claude", lambda: claude)
    monkeypatch.setattr("news_insight.public.benchmarks.benchmark_changes", broken)
    clock_at(monkeypatch, SPOTLIGHT_AT)

    result = runner.invoke(cli.app, ["spotlight", "write", "--date", "2026-11-03"])

    assert result.exit_code == 0, result.output
    assert claude.payloads[0]["benchmarks"] == {"changes": [], "new_models": []}


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


def test_benchmarks_collect_prints_each_site_and_exits_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_collect_all(session: Session, fetcher: SafeFetcher, now: datetime) -> dict[str, str]:
        seen["now"] = now
        return {"lmarena": "saved", "livebench": "selector_drift", "hf-trending": "unchanged"}

    monkeypatch.setattr(cli, "collect_all", fake_collect_all)

    result = runner.invoke(cli.app, ["benchmarks", "collect"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "lmarena: saved",
        "livebench: selector_drift",
        "hf-trending: unchanged",
    ]
    assert seen["now"].tzinfo is not None


def test_benchmarks_collect_dry_run_prints_the_top_and_writes_nothing(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.benchmarks.fakes import Router, deepswe_routes

    def no_session() -> Any:
        raise AssertionError("a dry run opens no database session")

    monkeypatch.setattr(cli, "session_scope", no_session)
    monkeypatch.setattr(cli, "_fetcher", lambda: deepswe_routes(Router(), recorded=True).fetcher())

    result = runner.invoke(
        cli.app, ["benchmarks", "collect", "--dry-run", "--site", "deepswe", "--top", "3"]
    )

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "deepswe: release 2026-09-22, 99 rows (not saved)"
    assert lines[1] == "  [v1.1] updated 2026-09-22"
    assert lines[2].split()[:3] == ["1", "gpt-6-astra", "[xhigh]"]
    assert lines[4].split()[:3] == ["3", "claude-opus-5", "[max]"]
    assert "  [v1] updated 2026-06-20" in lines
    assert db_session.scalar(select(BenchmarkSnapshot.id)) is None


def test_benchmarks_collect_dry_run_of_the_newer_sites(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.benchmarks.fakes import TbRouter, epoch_routes, osworld_routes, tau2_routes

    def no_session() -> Any:
        raise AssertionError("a dry run opens no database session")

    router = tau2_routes(osworld_routes(epoch_routes(TbRouter())))
    monkeypatch.setattr(cli, "session_scope", no_session)
    monkeypatch.setattr(cli, "_fetcher", router.fetcher)
    sites = ["terminal_bench", "epoch", "osworld", "tau2"]
    args = [part for site in sites for part in ("--site", site)]

    result = runner.invoke(cli.app, ["benchmarks", "collect", "--dry-run", *args, "--top", "2"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert [line.split(":")[0] for line in lines if not line.startswith(" ")] == sites
    assert "  [4.0] updated 2026-10-23" in lines
    first = lines[lines.index("  [4.0] updated 2026-10-23") + 1].split()
    assert first[:5] == ["1", "Claude", "Code", "·", "Opus"]
    assert "  [eci] updated 2026-10-26" in lines  # the newest model in the trimmed file
    assert "  [main] updated 2026-10-15" in lines
    assert "  [banking_knowledge] updated 2026-08-04" in lines
    assert db_session.scalar(select(BenchmarkSnapshot.id)) is None


@pytest.mark.parametrize(
    "args",
    [["--site", "deepswe"], ["--dry-run", "--site", "nope"]],
    ids=["site-without-dry-run", "unknown-site"],
)
def test_benchmarks_collect_rejects_bad_site_options(args: list[str]) -> None:
    result = runner.invoke(cli.app, ["benchmarks", "collect", *args])
    assert result.exit_code == 2
