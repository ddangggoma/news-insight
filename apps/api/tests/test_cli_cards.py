from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.cards import engines
from news_insight.cards.engines import EngineOutput, Quota
from news_insight.cards.schemas import CardInput
from news_insight.collect.contracts import RawItem
from news_insight.config import Settings
from news_insight.content.ingest import ingest_items
from tests.factories import build_source

pytestmark = pytest.mark.db
runner = CliRunner()


class Qwen:
    name = "qwen"

    def generate(self, inputs: list[CardInput]) -> EngineOutput:
        cards = [{"id": c.id, "title_ko": "카드", "summary_ko": [], "keywords": []} for c in inputs]
        return EngineOutput(raw={"cards": cards}, model=f"{self.name}-test")


class Agy(Qwen):
    name = "agy"

    def usage(self) -> Quota:
        return Quota(weekly=80, five_hour=60)


class Claude(Qwen):
    name = "claude"
    models: list[str] = []

    def __init__(self, *, cli: object, model: str) -> None:
        Claude.models.append(model)


@pytest.fixture(autouse=True)
def wire(db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "CARDS_LOCK", tmp_path / "cards.lock")

    @contextmanager
    def scope() -> Iterator[Session]:
        with db_session.begin_nested():
            yield db_session

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(cli, "_card_engines", lambda qwen_only: (None, Qwen()))
    settings = Settings(_env_file=None, card_agy_batch=1, card_agy_parallel=1)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    source = build_source()
    db_session.add(source)
    db_session.flush()
    ingest_items(
        db_session,
        source,
        [
            RawItem(stable_id=key, url=f"https://www.example.com/{key}", title=key.upper())
            for key in ("a", "b", "c")
        ],
        fetch_run=None,
        now=datetime(2026, 10, 4, tzinfo=UTC),
        canary=True,
    )


def test_cards_run_and_status() -> None:
    before = runner.invoke(cli.app, ["cards", "status"])
    run = runner.invoke(cli.app, ["cards", "run", "--qwen-only", "--budget", "60"])
    after = runner.invoke(cli.app, ["cards", "status"])

    assert "pending=3 reclassify=0 ready=0" in before.output
    assert run.exit_code == 0, run.output
    assert "ready=3 failed=0 kept_with_loss=0 reused=0 classified=0 batches: qwen=1" in run.output
    assert "pending=0 reclassify=0 ready=3" in after.output
    assert "last run" in after.output


@pytest.mark.parametrize("scheduled", [True, False])
def test_scheduled_run_pairs_antigravity_with_claude_haiku(
    monkeypatch: pytest.MonkeyPatch, scheduled: bool
) -> None:
    """Cards use Antigravity and Claude Haiku only (2026-10-13): Qwen stays out of a scheduled
    run, also when Claude sits out (quiet hours or the daily cap)."""
    monkeypatch.setattr(cli, "_card_engines", lambda qwen_only: ([Agy()], Qwen()))
    monkeypatch.setattr(cli, "_scheduled_claude", lambda settings: scheduled)
    monkeypatch.setattr(engines, "ClaudeEngine", Claude)
    Claude.models.clear()

    run = runner.invoke(cli.app, ["cards", "run", "--budget", "60"])

    assert run.exit_code == 0, run.output
    assert "ready=3" in run.output and "qwen=" not in run.output
    assert ("claude=" in run.output) is scheduled
    assert Claude.models == (["claude-haiku-5-5"] if scheduled else [])


def test_scheduled_claude_has_no_cap_or_quiet_hours_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 2026-10-29 (user request): every collected item gets a card, at any hour
    settings = Settings()
    assert (settings.card_claude_quiet_hours, settings.card_claude_daily_cap) == ("", 0)

    def no_count() -> None:
        raise AssertionError("an uncapped run needs no daily count")

    monkeypatch.setattr(cli, "session_scope", no_count)
    assert cli._scheduled_claude(settings) is True
