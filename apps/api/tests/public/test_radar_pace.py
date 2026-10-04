from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.public.periods import calendar_window, trailing_windows
from news_insight.public.radar import lifecycle, paced_cutoffs
from tests.public.seed import NOW, Spec, seed_corpus

pytestmark = pytest.mark.db

# last week, Sunday 20:00 KST: after the point this week has reached (Sunday 12:00 KST)
LATE_LAST_WEEK = Spec(
    "Agent OS late review",
    "verge",
    7 * 24 - 8,
    "ai",
    ("ai__ai_agents",),
    "market",
    "watch",
    "dx",
    60,
    ("AI 에이전트",),
)


@pytest.fixture(autouse=True)
def corpus(db_session: Session) -> dict[str, int]:
    return seed_corpus(db_session, extra=(LATE_LAST_WEEK,))


def themes(client: TestClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    response = client.get("/api/public/radar", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return {row["key"]: row for row in response.json()["themes"]}


def test_a_week_in_progress_is_compared_up_to_the_same_point(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    agents = themes(public_client, public_headers, period="week", key="2026-W40")["ai__ai_agents"]
    # the chart keeps the full count of last week; scoring stops at Sunday 12:00 there too
    assert agents["counts"][-2:] == [1, 2]
    assert agents["paced"][-2:] == [0, 2]
    assert agents["change"] is None  # nothing at this point last week
    assert agents["state"] == "surging"  # seen last week, so not "new"


def test_a_closed_week_is_compared_whole(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    agents = themes(public_client, public_headers, period="week", key="2026-W39")["ai__ai_agents"]
    assert agents["counts"][-1] == 1
    assert agents["paced"] is None


def test_paced_cutoffs_keep_the_elapsed_share() -> None:
    windows = trailing_windows(calendar_window("week", "2026-W40"), 3)
    cutoffs = paced_cutoffs(windows, NOW)
    assert cutoffs is not None
    assert [c.astimezone(UTC) for c in cutoffs] == [
        datetime(2026, 9, 20, 3, tzinfo=UTC),
        datetime(2026, 9, 27, 3, tzinfo=UTC),
        NOW,
    ]
    assert paced_cutoffs(trailing_windows(calendar_window("week", "2026-W39"), 3), NOW) is None
    # months differ in length: the same share, not the same number of days
    months = trailing_windows(calendar_window("month", "2026-10"), 2)
    september, october = paced_cutoffs(months, NOW) or []
    share = (NOW - months[1].start).total_seconds() / (31 * 86400)  # type: ignore[operator]
    assert (september - months[0].start).total_seconds() == pytest.approx(  # type: ignore[operator]
        share * 30 * 86400
    )
    assert october == NOW


def test_lifecycle_seen_before_overrides_paced_history() -> None:
    assert lifecycle([0, 0, 0, 3], sources=3) == "new"
    assert lifecycle([0, 0, 0, 3], sources=3, seen_before=True) == "surging"
