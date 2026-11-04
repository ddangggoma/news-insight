"""Plan 19 CLI: research enrich, patents index, insights backfill-stats."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import redis
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.patents.models import PatentMeta
from news_insight.research.models import EnrichStatus, ResearchDailyStat, ResearchMeta
from tests.documents import document, source
from tests.helpers import mock_fetcher

pytestmark = pytest.mark.db
runner = CliRunner()
ATTENTION = (Path(__file__).parent / "research/fixtures/openalex_attention.json").read_bytes()


@pytest.fixture(autouse=True)
def wire_cli(
    db_session: Session, redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session
        db_session.flush()

    def openalex(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.openalex.org", "CLI tests must not reach the network"
        return httpx.Response(200, headers={"content-type": "application/json"}, content=ATTENTION)

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(cli, "get_redis", lambda: redis_client)
    monkeypatch.setattr(cli, "_fetcher", lambda: mock_fetcher(openalex))


def test_research_enrich_looks_up_due_papers_and_prints_the_tally(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(
        db_session,
        src,
        "attention",
        refs=(("arxiv", "1706.03762"),),
        url="https://arxiv.org/abs/1706.03762",
    )

    result = runner.invoke(cli.app, ["research", "enrich", "--limit", "5"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == "attempted=1 ok=1 not_found=0 errors=0 stopped=-"
    row = db_session.get(ResearchMeta, paper.id)
    assert row is not None and row.status == EnrichStatus.OK


def test_patents_index_prints_the_tally(db_session: Session) -> None:
    office = source(
        db_session, "epo", category="patent_office", config={"mode": "epo_publications"}
    )
    item = document(
        db_session,
        office,
        "p",
        stable_id="epo:EP4815724NWA1",
        summary="EP4815724NWA1; IPC: G06N 3/08",
    )

    result = runner.invoke(cli.app, ["patents", "index"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == "indexed=1 removed=0"
    row = db_session.get(PatentMeta, item.id)
    assert row is not None and row.field == "ai"


def test_insights_backfill_stats_rebuilds_each_day(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    document(db_session, src, "p", published=datetime.now(UTC) - timedelta(days=2))

    result = runner.invoke(cli.app, ["insights", "backfill-stats", "--days", "3"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == "days=3 research_rows=1 patent_rows=0 signal_rows=1"
    assert len(db_session.scalars(select(ResearchDailyStat)).all()) == 1


def test_research_enrich_skips_while_another_run_holds_the_lock(
    db_session: Session, redis_client: redis.Redis
) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(db_session, src, "p", refs=(("arxiv", "1706.03762"),))
    redis_client.set("lock:research-enrich", "celery-run")

    result = runner.invoke(cli.app, ["research", "enrich"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == "skipped: another enrichment is running"
    assert db_session.get(ResearchMeta, paper.id) is None
    assert redis_client.get("lock:research-enrich") == b"celery-run"
