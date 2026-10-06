from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingFreeze, BriefingStatus
from news_insight.content.models import Item
from news_insight.digest.claude import ClaudeError, ClaudeResult
from news_insight.digest.models import Digest, DigestStatus
from news_insight.periodic import service
from tests.briefing.test_publish import seed

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 5, 21, 0, tzinfo=UTC)  # Monday 06:00 KST, 2026-W41
MONDAY = date(2026, 9, 28)  # 2026-W40


class FakeClaude:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail

    def generate(
        self,
        payload: dict[str, Any],
        *,
        schema: dict[str, Any],
        model: str,
        system: str | None = None,
        instruction: str | None = None,
    ) -> ClaudeResult:
        self.calls.append({"payload": payload, "system": system})
        if self.fail:
            raise ClaudeError("limit")
        ids = [i["id"] for i in payload["items"]]
        return ClaudeResult(
            structured={
                "headline": "주간 헤드라인",
                "tldr": ["하나", "둘", "셋", "넷"],
                "overview": "개요",
                "trends": [
                    {
                        "title": "흐름",
                        "body": "본문",
                        "item_ids": [*ids[:2], 999999],
                        "trajectory": "rising",
                        "companies": ["삼성전자"],
                    },
                    {"title": "근거 없음", "body": "b", "item_ids": [999998, 999999]},
                ],
                "companies": [{"name": "삼성전자", "summary": "s", "item_ids": [ids[0]]}],
                "watch_next": ["다음 주 발표"],
                "actions": ["벤치마크 정리"],
            },
            cost_usd=0.1,
            model="opus",
        )


def daily(db_session: Session, days: int) -> list[int]:
    """`days` published daily briefings from Monday of 2026-W40, citing the seeded items."""
    seed(db_session)
    ids = sorted(db_session.scalars(select(Item.id)))
    for offset in range(days):
        day = MONDAY + timedelta(days=offset)
        at = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        freeze = BriefingFreeze(
            briefing_date=day, frozen_at=at, candidate_ids=ids, taxonomy_revision="t"
        )
        digest = Digest(
            digest_date=day,
            version=1,
            status=DigestStatus.PUBLISHED,
            model="opus",
            generated_at=at,
            window_start=at,
            window_end=at,
            item_count=len(ids),
            input_hash="h",
            content={
                "headline": f"{day} 헤드라인",
                "tldr": ["요점"],
                "overview": "개요",
                "tracks": [],
                "insights": [{"title": f"인사이트 {offset}", "body": "본문", "item_ids": ids[:3]}],
            },
        )
        db_session.add_all([freeze, digest])
        db_session.flush()
        db_session.add(
            Briefing(
                briefing_date=day,
                version=1,
                status=BriefingStatus.PUBLISHED,
                freeze_id=freeze.id,
                digest_id=digest.id,
                input_hash="h",
                shortlist=[{"item_id": i, "track": "news", "score": 1} for i in ids],
                gates=[],
                published_at=at,
            )
        )
    db_session.flush()
    return ids


def test_weekly_briefing_keeps_only_evidence_from_daily_insights(db_session: Session) -> None:
    ids = daily(db_session, 4)
    client = FakeClaude()

    row = service.generate(
        db_session, kind="week", key="2026-W40", now=NOW, client=client, model="opus"
    )

    assert row is not None and row.status is DigestStatus.PUBLISHED and row.days == 4
    assert row.period_start == MONDAY and row.period_end == date(2026, 10, 5)
    payload = client.calls[0]["payload"]
    assert [d["date"] for d in payload["days"]][0] == "2026-09-28"
    assert {i["id"] for i in payload["items"]} == set(ids[:3])
    assert payload["companies"] and payload["companies"][0]["previous_count"] == 0
    assert "센싱 실무자" in client.calls[0]["system"]
    content = row.content
    assert content["tldr"] == ["하나", "둘", "셋"]
    assert [t["title"] for t in content["trends"]] == ["흐름"]
    assert content["trends"][0]["item_ids"] == sorted(ids[:2])
    again = service.generate(
        db_session, kind="week", key="2026-W40", now=NOW, client=client, model="opus"
    )
    assert again is row and len(client.calls) == 1


def test_short_periods_are_skipped_and_failures_fall_back(db_session: Session) -> None:
    daily(db_session, 3)
    assert (
        service.generate(
            db_session, kind="week", key="2026-W39", now=NOW, client=FakeClaude(), model="o"
        )
        is None
    )

    row = service.generate(
        db_session, kind="week", key="2026-W40", now=NOW, client=FakeClaude(fail=True), model="o"
    )

    assert row is not None and row.status is DigestStatus.FALLBACK and row.error == "limit"
    assert row.content["tldr"][0] == "2026-09-30 헤드라인"
    assert service.due(db_session, NOW) == [("week", "2026-W40"), ("month", "2026-09")]
