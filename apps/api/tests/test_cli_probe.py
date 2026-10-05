from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.sources.enums import Track
from tests.factories import build_source
from tests.helpers import serving
from tests.parsers.test_feed_probe import item, rss
from tests.sources.test_catalog import ENTRY, write_catalog

pytestmark = pytest.mark.db
runner = CliRunner()


def fresh_feed() -> bytes:
    now = datetime.now(UTC)
    dated = [format_datetime(now - timedelta(hours=n), usegmt=True) for n in (1, 2, 3)]
    return rss(*(item(n, date=date) for n, date in enumerate(dated, start=1)))


@pytest.fixture(autouse=True)
def wire_cli(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session
        db_session.flush()

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(cli, "_fetcher", lambda: serving(fresh_feed()))


def test_probe_catalog_reports_ready_sources(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app, ["sources", "probe-catalog", "--catalog", str(write_catalog(tmp_path, ENTRY))]
    )

    assert result.exit_code == 0, result.output
    assert "example-news" in result.output and "V0:ok V1:ok V2:ok V3:ok" in result.output
    assert "news 1/1" in result.output


def test_probe_reports_a_registered_source(db_session: Session) -> None:
    # V1 fails on the terms review; feeds no longer fail on robots.txt (feed reader, 2026-10-05)
    db_session.add(build_source(terms_url=None, config={"manual_review": True}))
    db_session.flush()

    result = runner.invoke(cli.app, ["sources", "probe", "example-news"])

    assert result.exit_code == 0, result.output
    assert "V1:FAIL" in result.output and "V3:ok" in result.output


def test_trends_movers_lists_the_biggest_gains(db_session: Session) -> None:
    source = build_source(track=Track.OSS)
    db_session.add(source)
    db_session.flush()
    now = datetime.now(UTC)
    for hours, stars in ((48, 100), (0, 180)):
        repo = RawItem(
            stable_id="a/b", url="https://github.com/a/b", title="a/b", metrics={"stars": stars}
        )
        ingest_items(
            db_session,
            source,
            [repo],
            fetch_run=None,
            now=now - timedelta(hours=hours),
            canary=True,
        )

    result = runner.invoke(cli.app, ["trends", "movers", "--metric", "stars", "--track", "oss"])

    assert result.exit_code == 0, result.output
    assert "+80" in result.output and "a/b" in result.output


def test_trends_movers_explains_an_empty_result() -> None:
    result = runner.invoke(cli.app, ["trends", "movers"])

    assert "no movers yet" in result.output
