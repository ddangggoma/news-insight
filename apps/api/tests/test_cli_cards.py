from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.cards.engines import EngineOutput
from news_insight.cards.schemas import CardInput
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from tests.factories import build_source

pytestmark = pytest.mark.db
runner = CliRunner()


class Qwen:
    name = "qwen"

    def generate(self, inputs: list[CardInput]) -> EngineOutput:
        cards = [{"id": c.id, "title_ko": "카드", "summary_ko": [], "keywords": []} for c in inputs]
        return EngineOutput(raw={"cards": cards}, model="qwen-test")


@pytest.fixture(autouse=True)
def wire(db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "CARDS_LOCK", tmp_path / "cards.lock")

    @contextmanager
    def scope() -> Iterator[Session]:
        with db_session.begin_nested():
            yield db_session

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(cli, "_card_engines", lambda qwen_only: (None, Qwen()))
    source = build_source()
    db_session.add(source)
    db_session.flush()
    ingest_items(
        db_session,
        source,
        [RawItem(stable_id="a", url="https://www.example.com/a", title="A")],
        fetch_run=None,
        now=datetime(2026, 10, 4, tzinfo=UTC),
        canary=True,
    )


def test_cards_run_and_status() -> None:
    before = runner.invoke(cli.app, ["cards", "status"])
    run = runner.invoke(cli.app, ["cards", "run", "--qwen-only", "--budget", "60"])
    after = runner.invoke(cli.app, ["cards", "status"])

    assert "pending=1 ready=0" in before.output
    assert run.exit_code == 0, run.output
    assert "ready=1 failed=0 batches: qwen=1" in run.output
    assert "pending=0 ready=1" in after.output
    assert "last run" in after.output
