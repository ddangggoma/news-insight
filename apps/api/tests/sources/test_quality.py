from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources import portfolio
from news_insight.sources.enums import SourceStatus, Track, ValidationStage
from news_insight.sources.quality import run_quality
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 10, tzinfo=UTC)


def source_with(
    db_session: Session,
    key: str,
    scopes: list[str | None],
    *,
    stage: ValidationStage = ValidationStage.V4,
    failed: int = 0,
    track: Track = Track.NEWS,
) -> object:
    source = build_source(key=key, validation_stage=stage, track=track)
    db_session.add(source)
    db_session.flush()
    rows = [
        RawItem(stable_id=f"{key}{i}", url=f"https://www.example.com/{key}/{i}", title=f"{key} {i}")
        for i in range(len(scopes) + failed)
    ]
    ingest_items(db_session, source, rows, fetch_run=None, now=NOW - timedelta(days=1), canary=True)
    items = list(
        db_session.scalars(select(Item).where(Item.source_id == source.id).order_by(Item.id))
    )
    for index, item in enumerate(items):
        status = CardStatus.READY if index < len(scopes) else CardStatus.FAILED
        db_session.add(
            ItemCard(
                item_id=item.id,
                status=status,
                title_ko="t",
                summary_ko=[],
                keywords=[],
                engine="agy",
                model="m",
                input_hash=item.content_hash,
                attempts=1,
                generated_at=NOW,
                scope=scopes[index] if index < len(scopes) else None,
            )
        )
    db_session.flush()
    return source


def test_low_relevance_pauses_and_high_relevance_promotes(db_session: Session) -> None:
    noisy = source_with(db_session, "noisy", ["irrelevant"] * 19 + ["dx"])
    great = source_with(
        db_session, "great", ["dx"] * 15 + ["dx_dependency"] * 5 + ["irrelevant"] * 5
    )
    okay = source_with(db_session, "okay", ["dx"] * 6 + ["irrelevant"] * 19)
    thin = source_with(db_session, "thin", ["irrelevant"] * 5)
    lossy = source_with(db_session, "lossy", ["dx"] * 20, failed=5)

    run = run_quality(db_session, now=NOW)

    assert run.paused == ["noisy"]
    assert noisy.status is SourceStatus.PAUSED and "low DX relevance 5%" in noisy.paused_reason
    assert run.promoted_v6 == ["great"]
    assert great.validation_stage is ValidationStage.V6 and great.status is SourceStatus.ACTIVE
    assert okay.validation_stage is ValidationStage.V4 and thin.status is SourceStatus.CANDIDATE
    assert lossy.validation_stage is ValidationStage.V4  # translation 80% < 95%


def test_a_track_past_its_goal_still_promotes_and_dry_run_changes_nothing(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # track targets are minimum goals, never caps (user decision 2026-10-05)
    monkeypatch.setitem(portfolio.TRACK_TARGETS, Track.NEWS, 0)
    best = source_with(db_session, "best", ["dx"] * 25)
    preview = run_quality(db_session, now=NOW, apply=False)
    assert preview.passed_v5 == ["best"] and best.validation_stage is ValidationStage.V4

    run = run_quality(db_session, now=NOW)

    assert run.track_full == [] and run.promoted_v6 == ["best"]
    assert best.validation_stage is ValidationStage.V6 and best.status is SourceStatus.ACTIVE


def test_console_lists_source_quality(db_session: Session) -> None:
    from news_insight.console.queries import source_quality

    source_with(db_session, "noisy", ["irrelevant"] * 19 + ["dx"])
    source_with(db_session, "great", ["dx"] * 20)

    worst = source_quality(db_session, now=NOW, order="worst", limit=10)
    best = source_quality(db_session, now=NOW, order="best", limit=10)

    assert [row.key for row in worst] == ["noisy", "great"]
    assert [row.key for row in best] == ["great", "noisy"]
    assert worst[0].relevance == 0.05 and best[0].translation == 1.0
