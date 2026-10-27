"""The radar baseline starts once collection was running (2026-10-27 audit: with collection
started on 2026-10-04, 56 of 62 themes read "급상승" and z reached +41497σ)."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.public.periods import calendar_window, trailing_windows
from news_insight.public.radar import baseline, lifecycle, z_score
from tests.public.seed import NOW, Spec, seed_corpus

pytestmark = [pytest.mark.db, pytest.mark.collection_start]

THEME = "robotics_mobility__humanoid_embodied"
# NOW is Sunday 2026-10-04 12:00 KST (W40); W37 started 2026-09-07
COLLECTION_STARTED = 24 * 25  # Wednesday of W37, hours before NOW


def report(title: str, source: str, hours_ago: float) -> Spec:
    return Spec(
        title, source, hours_ago, "robotics_mobility", (THEME,), "launch", keywords=("휴머노이드",)
    )


# the first day's backfill stamps twenty reports into W37, then three a week, then nine
BACKFILL = tuple(
    report(f"backfill {n:02d}", "verge", COLLECTION_STARTED - n * 0.1) for n in range(20)
)
STEADY = tuple(
    report(f"week {week} report {n}", ("verge", "etnews", "github")[n], 24 * (3 + 7 * week) + n)
    for week in (1, 2)
    for n in range(3)
)
NOW_REPORTS = tuple(
    report(f"this week {n}", ("verge", "etnews", "github")[n % 3], 1 + n) for n in range(9)
)


def radar(client: TestClient, headers: dict[str, str], **params: Any) -> Any:
    response = client.get("/api/public/radar", params={"period": "week", **params}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_baseline_leaves_out_windows_before_and_at_the_start_of_collection() -> None:
    windows = trailing_windows(calendar_window("week", "2026-W40"), 8)
    started = NOW - timedelta(hours=COLLECTION_STARTED)
    span = baseline(windows, started)
    assert (span.start, span.windows, span.enough) == (5, 2, True)  # W38 and W39
    assert baseline(windows, windows[5].start).start == 5  # a window starting with it counts
    assert baseline(windows, NOW - timedelta(days=3)).windows == 0
    assert not baseline(windows, None).enough  # nothing collected yet
    assert baseline(windows, NOW - timedelta(days=400)).windows == 7


def test_z_and_state_need_two_baseline_windows() -> None:
    assert z_score([0, 0, 0, 0, 20, 3, 3, 9], start=5) == 3.46
    assert z_score([0, 0, 0, 0, 0, 0, 20, 9], start=7) is None
    assert lifecycle([0, 0, 0, 0, 20, 3, 3, 9], sources=3, start=5) == "surging"
    assert lifecycle([0, 0, 0, 0, 0, 0, 0, 9], sources=3, start=7) is None
    assert lifecycle([0, 0, 0, 0, 0, 0, 3, 9], sources=3, start=6) is None


def test_radar_scores_against_the_windows_after_collection_started(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    seed_corpus(db_session, extra=(*BACKFILL, *STEADY, *NOW_REPORTS))
    body = radar(public_client, public_headers, key="2026-W40")
    assert {k: body["baseline"][k] for k in ("start", "windows", "required", "enough")} == {
        "start": 5,
        "windows": 2,
        "required": 2,
        "enough": True,
    }
    theme = {t["key"]: t for t in body["themes"]}[THEME]
    assert theme["counts"][-4:] == [20, 3, 3, 9]
    # against W38–W39 only: the backfill neither inflates the mean nor the noise
    assert (theme["z"], theme["state"]) == (3.46, "surging")
    assert sum(theme["baseline_tracks"].values()) == 6
    surge = next(s for s in body["signals"] if s["tone"] == "surge")
    assert surge["title"] and "직전 2주 같은 시점 평균 3.0건" in surge["detail"]


def test_without_enough_baseline_windows_scores_are_null_and_cards_stay_off(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    # the shared corpus starts on Thursday of W39: no full window before the current one
    seed_corpus(db_session, extra=NOW_REPORTS)
    body = radar(public_client, public_headers, key="2026-W40")
    assert {k: body["baseline"][k] for k in ("start", "windows", "enough")} == {
        "start": 7,
        "windows": 0,
        "enough": False,
    }
    assert body["baseline"]["collected_since"] is not None
    for topic in (*body["fields"], *body["themes"], *body["keywords"]):
        assert topic["z"] is None and topic["state"] is None
        assert topic["change"] is None  # the previous window is before the baseline
    assert body["signals"] == []
    # keywords are still listed, by volume, and none is a "debut" just because collection is new
    assert [k["key"] for k in body["keywords"]][:1] == ["휴머노이드"]
    assert not any(k["debut"] for k in body["keywords"])
    month = radar(public_client, public_headers, period="month", key="2026-10")
    assert month["baseline"]["windows"] == 0 and month["signals"] == []
    assert all(t["state"] is None for t in month["themes"])


def test_kpis_carry_paced_counts_for_a_window_in_progress(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    # Sunday 20:00 last week is after the point this week has reached (Sunday 12:00)
    late = report("late last week", "verge", 7 * 24 - 8)
    seed_corpus(db_session, extra=(*STEADY, late))
    current = radar(public_client, public_headers, key="2026-W40")["kpis"]
    assert current["paced"] is not None
    assert current["items"][-2] == current["paced"]["items"][-2] + 1
    assert current["paced"]["items"][-1] == current["items"][-1]
    closed = radar(public_client, public_headers, key="2026-W39")["kpis"]
    assert closed["paced"] is None


def test_calendar_usual_level_starts_after_collection(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    def frontier(title: str, hours_ago: float) -> Spec:
        return Spec(title, "verge", hours_ago, "frontier", (), keywords=("양자",))

    # collection starts on a Sunday three weeks ago with a backfill of twenty, then one report
    # on each of the next two Sundays, then nine today
    backfill = tuple(frontier(f"backfill {n:02d}", 24 * 21 + n * 0.1) for n in range(20))
    usual = (frontier("usual 1", 24 * 14 + 1), frontier("usual 2", 24 * 7 + 1))
    today = tuple(frontier(f"today {n}", 1 + n * 0.1) for n in range(9))
    seed_corpus(db_session, extra=(*backfill, *usual, *today))
    anomalies = radar(public_client, public_headers, key="2026-W40")["calendar"]["anomalies"]
    # the backfill day is neither an event (no usual level before it) nor part of the usual
    # level (it would make today's nine look ordinary)
    assert [(a["day"], a["count"], a["expected"]) for a in anomalies] == [("2026-10-04", 9, 1.0)]
