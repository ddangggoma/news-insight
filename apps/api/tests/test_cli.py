from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from news_insight import cli
from news_insight.net.safe_fetch import SafeFetcher
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
