import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.cards.models import CardRun
from news_insight.ops import checks, host, service
from news_insight.ops.checks import check_card_output, check_host
from news_insight.ops.engines import card_engine_health
from news_insight.ops.models import Severity

NOW = datetime(2026, 10, 8, 5, 0, tzinfo=UTC)
GB = 1024**3


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def set(self, key: str, value: str, ex: int) -> None:
        self.data[key] = value

    def get(self, key: str) -> Any:
        return self.data.get(key)


def runner(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
    out = {
        "sysctl": "total = 19456.00M  used = 18949.88M  free = 506.12M  (encrypted)\n",
        "memory_pressure": "...\nSystem-wide memory free percentage: 9%\n",
    }[args[0]]
    return subprocess.CompletedProcess(args, 0, out, "")


def test_snapshot_parses_swap_memory_and_qwen_and_goes_stale() -> None:
    snapshot = host.collect(
        lm_url="http://lm:1234/",
        lm_model="qwen/q",
        now=NOW,
        runner=runner,
        http=lambda url: {
            "data": [
                {"id": "qwen/q", "state": "not-loaded", "loaded_context_length": None},
                {"id": "qwen/q:2", "state": "loaded", "loaded_context_length": 16384},
                {"id": "other", "state": "loaded", "loaded_context_length": 4096},
            ]
        },
    )
    assert snapshot["swap_total_mb"] == 19456 and snapshot["swap_used_mb"] == 18950
    assert snapshot["memory_free_pct"] == 9
    assert snapshot["qwen"] == {
        "model": "qwen/q",
        "state": "loaded",
        "context": 16384,
        "instances": 1,
    }
    client = FakeRedis()
    host.save(client, snapshot)  # type: ignore[arg-type]
    assert host.load(client, now=NOW)["stale"] is False  # type: ignore[arg-type,index]
    assert host.load(client, now=NOW + timedelta(hours=1))["stale"] is True  # type: ignore[arg-type,index]


def test_snapshot_records_the_mac_data_volume() -> None:
    seen: list[Path] = []

    def usage(path: Path) -> SimpleNamespace:
        seen.append(path)
        return SimpleNamespace(total=926 * GB, used=879 * GB, free=47 * GB)

    snapshot = host.collect(
        lm_url="http://lm:1234",
        lm_model="qwen/q",
        now=NOW,
        runner=runner,
        http=lambda url: {},
        disk_usage=usage,
    )

    assert seen == [Path.home()]  # the Data volume, where Docker.raw lives; "/" is the system one
    assert snapshot["disk_total_bytes"] == 926 * GB and snapshot["disk_free_bytes"] == 47 * GB


def test_snapshot_skips_the_disk_when_it_cannot_be_read() -> None:
    def broken(path: Path) -> SimpleNamespace:
        raise OSError("gone")

    snapshot = host.collect(
        lm_url="http://lm:1234",
        lm_model="qwen/q",
        now=NOW,
        runner=runner,
        http=lambda url: {},
        disk_usage=broken,
    )

    assert "disk_free_bytes" not in snapshot and snapshot["memory_free_pct"] == 9


def test_host_snapshot_command_prints_the_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from news_insight import cli
    from news_insight.config import Settings

    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("news_insight.scheduling.redis_guards.get_redis", lambda: None)
    monkeypatch.setattr(host, "save", lambda client, snapshot: saved.append(snapshot))
    monkeypatch.setattr(
        host,
        "collect",
        lambda **_: {
            "memory_free_pct": 40,
            "disk_total_bytes": 926 * GB,
            "disk_free_bytes": 47 * GB,
        },
    )

    result = CliRunner().invoke(cli.app, ["ops", "host-snapshot"])

    assert result.exit_code == 0, result.output
    assert "disk 47.0/926.0 GB free (5.1%)" in result.output and len(saved) == 1


def test_host_disk_warns_under_10_and_is_critical_under_5_percent() -> None:
    def disk(free_gb: int, **extra: Any) -> list[checks.Finding]:
        return check_host({"disk_total_bytes": 926 * GB, "disk_free_bytes": free_gb * GB, **extra})

    assert disk(100) == []
    [warning] = disk(47)
    assert warning.key == "host_disk" and warning.severity == Severity.WARNING
    assert "47.0/926.0 GB" in warning.detail and "Docker.raw" in warning.detail
    [critical] = disk(40)
    assert critical.severity == Severity.CRITICAL
    assert disk(40, stale=True) == []
    assert "host_disk" not in service.CONSOLE_ONLY  # it takes Docker down: mailed with the rest


def test_host_findings_and_console_only_alerts() -> None:
    full = {
        "swap_total_mb": 1000,
        "swap_used_mb": 950,
        "memory_free_pct": 30,
        "qwen": {"state": "not-loaded"},
    }
    assert {f.key for f in check_host(full)} == {"host_memory", "qwen_unloaded"}
    assert check_host({**full, "stale": True}) == []
    assert check_host({"swap_total_mb": 1000, "swap_used_mb": 100, "memory_free_pct": 40}) == []
    assert "host_memory" in service.CONSOLE_ONLY and "cards_zero" in service.CONSOLE_ONLY


@pytest.mark.db
def test_engine_health_and_zero_run_streak(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_session.add(
        CardRun(started_at=NOW - timedelta(hours=3), ready=5, batches={"qwen": 1}, quota={})
    )
    for minutes in range(10, 80, 10):
        db_session.add(
            CardRun(
                started_at=NOW - timedelta(minutes=minutes),
                batches={},
                quota={},
                note="agy quota reserved: switching to qwen; qwen failed: 400 Bad Request",
            )
        )
    db_session.flush()

    health = card_engine_health(db_session)

    assert health.zero_runs == 7
    qwen = next(e for e in health.engines if e.name == "qwen")
    assert (
        qwen.last_batch_at == NOW - timedelta(hours=3)
        and qwen.latest_note == "qwen failed: 400 Bad Request"
    )
    monkeypatch.setattr(checks, "pending_count", lambda session: 10)
    [finding] = check_card_output(db_session)
    assert finding.key == "cards_zero" and "qwen failed" in finding.detail
    monkeypatch.setattr(checks, "pending_count", lambda session: 0)
    assert check_card_output(db_session) == []


@pytest.mark.db
def test_ops_status_api(
    console_client: TestClient,
    headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "load", lambda client, now: {"swap_used_mb": 1, "stale": False})
    monkeypatch.setattr("news_insight.scheduling.redis_guards.get_redis", lambda: None)

    body = console_client.get("/api/admin/ops/status", headers=headers).json()

    assert body["host"] == {"swap_used_mb": 1, "stale": False}
    assert [e["name"] for e in body["cards"]["engines"]] == ["claude", "codex", "agy", "qwen"]
