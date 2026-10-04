from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.briefing.models import BriefingStatus
from news_insight.briefing.selection import SelectionRules
from news_insight.briefing.service import current_briefing, failing, freeze, publish
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.digest.bundle import digest_window
from news_insight.digest.claude import ClaudeResult
from news_insight.sources.enums import Region, Track, ValidationStage
from tests.factories import build_source

pytestmark = pytest.mark.db
DAY = date(2026, 10, 5)
START, _ = digest_window(DAY)
FREEZE_AT = datetime(2026, 10, 4, 19, 40, tzinfo=UTC)  # 04:40 KST on DAY
RULES = SelectionRules(
    size=8,
    track_min={"news": 3, "research_ip": 1, "oss": 1, "community": 1},
    track_gate_min={"news": 3, "research_ip": 1, "oss": 1, "community": 1},
    domain_cap=0.25,
    korean_min=0.25,
    official_min=0.25,
    independent_min=0.25,
)


class FakeClaude:
    calls = 0

    def generate(
        self, payload: dict[str, Any], *, schema: dict[str, Any], model: str
    ) -> ClaudeResult:
        FakeClaude.calls += 1
        ids = [i["id"] for t in payload["tracks"] for c in t["categories"] for i in c["items"]]
        content = {
            "headline": "헤드라인",
            "overview": "개요",
            "tracks": [
                {
                    "track": "news",
                    "summary": "요약",
                    "categories": [
                        {
                            "category": "independent_media",
                            "headline": "h",
                            "points": [{"text": "p", "item_ids": ids[:1]}],
                        }
                    ],
                }
            ],
            "insights": [{"title": "i", "body": "b", "item_ids": ids[:2]}],
        }
        return ClaudeResult(structured=content, cost_usd=0.1, model="opus")


SPECS = [
    ("verge", Track.NEWS, "independent_media", Region.GLOBAL_EN),
    ("etnews", Track.NEWS, "independent_media", Region.KR),
    ("zdnet-kr", Track.NEWS, "independent_media", Region.KR),
    ("samsung", Track.NEWS, "official_vendor", Region.KR),
    ("fcc", Track.NEWS, "government", Region.GLOBAL_EN),
    ("arxiv", Track.RESEARCH_IP, "academic_paper", Region.GLOBAL_EN),
    ("github", Track.OSS, "oss_trend", Region.GLOBAL_EN),
    ("hn", Track.COMMUNITY, "dev_forum", Region.GLOBAL_EN),
]


def seed(
    db_session: Session,
    specs: list[tuple[str, Track, str, Region]] = SPECS,
    when: datetime = START + timedelta(hours=3),
) -> None:
    for key, track, category, region in specs:
        source = db_session.scalars(
            select(__import__("news_insight.sources.models", fromlist=["Source"]).Source).where(
                __import__("news_insight.sources.models", fromlist=["Source"]).Source.key == key
            )
        ).one_or_none()
        if source is None:
            source = build_source(
                key=key,
                name=key,
                track=track,
                category=category,
                region=region,
                language="ko" if region is Region.KR else "en",
                official_domain=f"{key}.com",
                validation_stage=ValidationStage.V4,
            )
            db_session.add(source)
            db_session.flush()
        url = f"https://{key}.com/{when.timestamp()}"
        ingest_items(
            db_session,
            source,
            [RawItem(stable_id=url, url=url, title=f"{key} 기사")],
            fetch_run=None,
            now=when,
            canary=True,
        )
        item = db_session.scalars(select(Item).where(Item.url == url)).one()
        db_session.add(
            ItemCard(
                item_id=item.id,
                status=CardStatus.READY,
                title_ko=f"{key} 카드",
                summary_ko=[],
                keywords=[key],
                engine="agy",
                model="m",
                input_hash=item.content_hash,
                attempts=0,
                generated_at=when,
                scope="dx",
                relevance=70,
                businesses=["mx"],
            )
        )
    db_session.flush()


def test_publish_passes_gates_and_is_idempotent(db_session: Session) -> None:
    seed(db_session)

    first = publish(
        db_session,
        briefing_date=DAY,
        now=FREEZE_AT,
        client=FakeClaude(),
        model="opus",
        rules=RULES,
        with_strategy=False,
    )
    calls = FakeClaude.calls
    again = publish(
        db_session,
        briefing_date=DAY,
        now=FREEZE_AT + timedelta(minutes=20),
        client=FakeClaude(),
        model="opus",
        rules=RULES,
        with_strategy=False,
    )

    assert first.status is BriefingStatus.PUBLISHED, failing(first.gates)
    assert len(first.shortlist) == 8 and first.digest_id is not None
    assert again.id == first.id and FakeClaude.calls == calls
    assert current_briefing(db_session) is first


def test_freeze_snapshot_ignores_late_items(db_session: Session) -> None:
    seed(db_session)
    snapshot = freeze(db_session, briefing_date=DAY, now=FREEZE_AT)
    seed(db_session, [("late", Track.NEWS, "independent_media", Region.KR)])

    assert (
        freeze(db_session, briefing_date=DAY, now=FREEZE_AT + timedelta(minutes=5)).id
        == snapshot.id
    )
    briefing = publish(
        db_session,
        briefing_date=DAY,
        now=FREEZE_AT,
        client=FakeClaude(),
        model="opus",
        rules=RULES,
        with_strategy=False,
    )
    late = db_session.scalars(select(Item).where(Item.title == "late 기사")).one()
    assert late.id not in {entry["item_id"] for entry in briefing.shortlist}


def test_failed_gate_blocks_and_keeps_the_previous_briefing(db_session: Session) -> None:
    seed(db_session)
    yesterday = publish(
        db_session,
        briefing_date=DAY,
        now=FREEZE_AT,
        client=FakeClaude(),
        model="opus",
        rules=RULES,
        with_strategy=False,
    )
    next_day = DAY + timedelta(days=1)
    seed(
        db_session,
        [s for s in SPECS if s[3] is not Region.KR],
        when=START + timedelta(days=1, hours=3),
    )

    blocked = publish(
        db_session,
        briefing_date=next_day,
        now=FREEZE_AT + timedelta(days=1),
        client=FakeClaude(),
        model="opus",
        rules=RULES,
        with_strategy=False,
    )

    assert blocked.status is BriefingStatus.BLOCKED
    assert "한국 출처 비중" in failing(blocked.gates)
    assert current_briefing(db_session) == yesterday


def test_console_briefing_api(
    db_session: Session, console_client: object, headers: dict[str, str]
) -> None:
    from fastapi.testclient import TestClient

    client: TestClient = console_client  # type: ignore[assignment]
    seed(db_session)
    publish(
        db_session,
        briefing_date=DAY,
        now=FREEZE_AT,
        client=FakeClaude(),
        model="opus",
        rules=RULES,
        with_strategy=False,
    )

    latest = client.get("/api/admin/briefings/latest", headers=headers).json()
    listed = client.get("/api/admin/briefings", headers=headers).json()

    assert latest["status"] == "published" and latest["is_current"] is True
    assert sum(len(section["items"]) for section in latest["sections"]) == 8
    assert latest["digest"]["status"] == "published"
    assert {gate["name"] for gate in latest["gates"]} >= {"korean", "domain_cap", "evidence"}
    assert listed[0]["shortlist"] == 8 and listed[0]["failing"] == []
