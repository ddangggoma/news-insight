from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.collect.models import FetchOutcome, FetchRun
from news_insight.console import routes
from news_insight.content.ingest import ingest_items
from news_insight.sources.enums import Region, SourceStatus, Track, ValidationStage
from news_insight.sources.ladder import CheckResult, record_check
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def seed(db_session: Session) -> None:
    news = build_source(key="news-a", name="News A", validation_stage=ValidationStage.V3)
    kr = build_source(key="kr-b", name="한국 B", region=Region.KR, language="ko")
    oss = build_source(key="oss-c", name="OSS C", track=Track.OSS)
    db_session.add_all([news, kr, oss])
    db_session.flush()
    ingest_items(
        db_session,
        news,
        [RawItem(stable_id="1", url="https://www.example.com/1", title="Galaxy")],
        fetch_run=None,
        now=NOW,
        canary=True,
    )
    db_session.add(FetchRun(source_id=news.id, started_at=NOW, outcome=FetchOutcome.SUCCESS))
    record_check(db_session, kr, ValidationStage.V0, CheckResult(passed=True))


def test_sources_are_filtered_and_paged(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed(db_session)

    all_rows = console_client.get("/api/admin/sources?size=2", headers=headers).json()
    kr_only = console_client.get("/api/admin/sources?region=kr", headers=headers).json()
    searched = console_client.get("/api/admin/sources?q=News", headers=headers).json()

    assert (all_rows["total"], len(all_rows["items"]), all_rows["size"]) == (3, 2, 2)
    assert [row["key"] for row in kr_only["items"]] == ["kr-b"]
    assert [row["key"] for row in searched["items"]] == ["news-a"]
    assert searched["items"][0]["items_total"] == 1


def test_source_detail_includes_history(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed(db_session)

    detail = console_client.get("/api/admin/sources/kr-b", headers=headers).json()
    news = console_client.get("/api/admin/sources/news-a", headers=headers).json()

    assert detail["source"]["validation_stage"] == "V0"
    assert [event["stage"] for event in detail["events"]] == ["V0"]
    assert [item["title"] for item in news["items"]] == ["Galaxy"]
    assert news["runs"][0]["outcome"] == "success"
    assert console_client.get("/api/admin/sources/missing", headers=headers).status_code == 404


def test_pause_resume_and_collect_now(
    console_client: TestClient,
    headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(db_session)
    queued: list[int] = []
    monkeypatch.setattr(routes, "enqueue_collection", queued.append)

    paused = console_client.post(
        "/api/admin/sources/news-a/pause", headers=headers, json={"reason": "점검"}
    ).json()
    resumed = console_client.post("/api/admin/sources/news-a/resume", headers=headers).json()
    collected = console_client.post("/api/admin/sources/news-a/collect", headers=headers).json()
    conflict = console_client.post("/api/admin/sources/news-a/resume", headers=headers)

    assert (paused["status"], paused["paused_reason"]) == (SourceStatus.PAUSED.value, "점검")
    assert resumed["status"] == SourceStatus.CANDIDATE.value
    assert collected == {"queued": True} and len(queued) == 1
    assert conflict.status_code == 409
