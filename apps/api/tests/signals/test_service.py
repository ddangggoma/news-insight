from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.signals.models import RadarSignalSnapshot
from news_insight.signals.service import ensure, evidence, for_day, radar_path, snapshot
from tests.public.seed import NOW, Spec, seed_corpus

pytestmark = pytest.mark.db
DAY = date(2026, 10, 4)
# one report in each earlier week, so the radar has a baseline to compare against
BASELINE = tuple(
    Spec(f"Weekly roundup {weeks}", "verge", 24 * 7 * weeks + 1, "ai", ("ai__foundation_models",))
    for weeks in range(2, 8)
)


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(RadarSignalSnapshot)) or 0


def test_snapshot_stores_this_and_last_weeks_cards(db_session: Session) -> None:
    seed_corpus(db_session, extra=BASELINE)
    rows = snapshot(db_session, day=DAY, now=NOW)
    assert [(r.window_key, r.is_current, r.tone, r.focus_key) for r in rows] == [
        ("2026-W40", True, "new", "oled")
    ]
    assert radar_path(rows[0]) == "/radar/week/2026-W40?focus=keyword:oled"
    assert evidence(for_day(db_session, DAY)) == [
        {
            "signal": "신규 기술",
            "window": "2026-W40 (진행 중)",
            "topic": "OLED",
            "detail": rows[0].detail,
        }
    ]


def test_snapshot_replaces_and_ensure_reuses(db_session: Session) -> None:
    seed_corpus(db_session, extra=BASELINE)
    ensure(db_session, day=DAY, now=NOW)
    ensure(db_session, day=DAY, now=NOW)
    snapshot(db_session, day=DAY, now=NOW)
    assert count(db_session) == 1


def test_for_day_keeps_one_card_per_topic_this_week_first(db_session: Session) -> None:
    def row(window: str, current: bool, tone: str, key: str) -> RadarSignalSnapshot:
        return RadarSignalSnapshot(
            snapshot_date=DAY,
            period="week",
            window_key=window,
            is_current=current,
            tone=tone,
            focus_kind="theme",
            focus_key=key,
            title=key,
            detail="",
            score=1.0,
            created_at=NOW,
        )

    db_session.add_all(
        [
            row("2026-W39", False, "surge", "ai__ai_agents"),
            row("2026-W40", True, "cool", "ai__ai_agents"),
            row("2026-W40", True, "surge", "display_av__display_panel"),
        ]
    )
    db_session.flush()
    assert [(r.window_key, r.tone) for r in for_day(db_session, DAY)] == [
        ("2026-W40", "surge"),
        ("2026-W40", "cool"),
    ]
