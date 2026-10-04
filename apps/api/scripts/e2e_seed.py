"""Seed a throwaway E2E database with two published briefings (fixtures, not real news).

Usage: DATABASE_URL=...news_insight_e2e uv run python scripts/e2e_seed.py
Refuses to touch a database whose name does not end in `_e2e`.
"""

import hashlib
import os
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingFreeze, BriefingStatus
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item
from news_insight.digest.models import Digest, DigestStatus
from news_insight.sources.enums import (
    AccessMethod,
    PollClass,
    Region,
    SourceStatus,
    StorageRight,
    Track,
    ValidationStage,
)
from news_insight.sources.models import Source
from news_insight.strategy.models import StrategyRun, StrategyStatus
from news_insight.strategy.personas import PERSONAS
from news_insight.taxonomy.catalog import TAXONOMY_REVISION

# Relative to the run: the reader feed shows the last 7 days by default.
NOW = datetime.now(UTC).replace(microsecond=0)
TODAY = NOW.astimezone(ZoneInfo("Asia/Seoul")).date()
YESTERDAY = TODAY - timedelta(days=1)

SOURCES = [
    ("etnews", "전자신문", Track.NEWS, "independent_media", Region.KR),
    ("samsung-newsroom", "Samsung Newsroom", Track.NEWS, "official_vendor", Region.KR),
    ("the-verge", "The Verge", Track.NEWS, "independent_media", Region.GLOBAL_EN),
    ("arxiv", "arXiv", Track.RESEARCH_IP, "academic_paper", Region.GLOBAL_EN),
    ("github", "GitHub Trending", Track.OSS, "oss_trend", Region.GLOBAL_EN),
    ("hn", "Hacker News", Track.COMMUNITY, "dev_forum", Region.GLOBAL_EN),
]

# (source, original title, Korean title, summary, field, theme, businesses, impact)
CARDS: list[tuple[str, str, str, list[str], str, str, list[str], str]] = [
    (
        "etnews",
        "삼성, 온디바이스 AI 칩 공개",
        "삼성, 차세대 온디바이스 AI 칩 공개",
        ["NPU 성능을 2배로 높였다.", "갤럭시 S30에 처음 탑재된다."],
        "mobile_edge",
        "mobile_edge__smartphone_compute",
        ["mx"],
        "opportunity",
    ),
    (
        "samsung-newsroom",
        "Samsung unveils Micro RGB TV",
        "삼성, 마이크로 RGB TV 공개",
        ["백라이트 없는 자발광 구조다.", "내년 상반기 출시 예정이다."],
        "display_media",
        "display_media__oled_microled",
        ["vd"],
        "opportunity",
    ),
    (
        "the-verge",
        "Apple foldable iPhone enters production",
        "애플 폴더블 아이폰 양산 돌입",
        ["힌지 공급망이 확정됐다.", "2027년 출시가 유력하다."],
        "mobile_edge",
        "mobile_edge__smartphone_compute",
        ["mx"],
        "risk",
    ),
    (
        "the-verge",
        "Matter 1.5 adds energy management",
        "매터 1.5, 가전 에너지 관리 기능 추가",
        ["스마트홈 표준에 전력 관리 API가 생겼다."],
        "network_comms",
        "network_comms__short_range_wireless",
        ["da"],
        "watch",
    ),
    (
        "arxiv",
        "Quantized LLMs for phones",
        "스마트폰용 4비트 양자화 LLM 기법",
        ["메모리 사용량을 60% 줄였다.", "정확도 손실은 1% 미만이다."],
        "ai_data",
        "ai_data__edge_ai",
        ["mx"],
        "opportunity",
    ),
    (
        "arxiv",
        "6G semantic communication survey",
        "6G 시맨틱 통신 연구 동향 서베이",
        ["표준화 일정과 핵심 과제를 정리했다."],
        "network_comms",
        "network_comms__fiveg_sixg",
        ["networks"],
        "watch",
    ),
    (
        "github",
        "llama.cpp adds NPU backend",
        "llama.cpp, 모바일 NPU 백엔드 추가",
        ["엑시노스와 스냅드래곤 NPU를 지원한다."],
        "open_source",
        "open_source__project_trends",
        ["mx"],
        "opportunity",
    ),
    (
        "hn",
        "Discussion: smart TV ads backlash",
        "스마트 TV 광고 강제 노출에 개발자 반발",
        ["플랫폼 광고 정책에 대한 비판이 커졌다."],
        "product_market",
        "product_market__consumer_electronics",
        ["vd"],
        "risk",
    ),
]


def _source(key: str, name: str, track: Track, category: str, region: Region) -> Source:
    return Source(
        key=key,
        name=name,
        track=track,
        category=category,
        access_method=AccessMethod.FEED,
        endpoint_url=f"https://{key}.example/feed.xml",
        official_domain=f"{key}.example",
        operator=name,
        region=region,
        language="ko" if region is Region.KR else "en",
        poll_class=PollClass.NEWS,
        dx_relevance="E2E fixture",
        terms_url=None,
        storage_right=StorageRight.EXCERPT_ALLOWED,
        config={},
        validation_stage=ValidationStage.V6,
        status=SourceStatus.ACTIVE,
    )


def _reset(url: str) -> None:
    if not (make_url(url).database or "").endswith("_e2e"):
        sys.exit("refusing to seed a database whose name does not end in _e2e")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")


def _ids_by_track(items: list[Item]) -> dict[str, list[int]]:
    tracks: dict[str, list[int]] = {}
    for item in items:
        tracks.setdefault(item.track.value, []).append(item.id)
    return tracks


def _digest(day: date, items: list[Item], now: datetime) -> Digest:
    ids = [item.id for item in items]
    content: dict[str, Any] = {
        "headline": "온디바이스 AI 경쟁 본격화, 폴더블 시장 재편 신호",
        "overview": (
            "삼성의 NPU 강화와 애플 폴더블 양산이 같은 날 확인됐다. "
            "모바일 AI와 폼팩터 경쟁이 동시에 가속하고 있다."
        ),
        "tracks": [
            {"track": track, "summary": f"{track} 트랙 요약", "categories": []}
            for track in _ids_by_track(items)
        ],
        "insights": [
            {
                "title": "온디바이스 AI가 플래그십 차별화의 중심",
                "body": "칩·모델·오픈소스가 동시에 모바일 NPU로 수렴한다.",
                "item_ids": ids[:1] + ids[4:5] + ids[6:7],
            },
            {
                "title": "폴더블 경쟁 구도 변화",
                "body": "애플 진입으로 폴더블 프리미엄 가격대 경쟁이 예상된다.",
                "item_ids": ids[0:1] + ids[2:3],
            },
        ],
    }
    return Digest(
        digest_date=day,
        version=1,
        status=DigestStatus.PUBLISHED,
        model="fixture",
        generated_at=now,
        window_start=now - timedelta(days=1),
        window_end=now,
        item_count=len(items),
        input_hash=hashlib.sha256(str(day).encode()).hexdigest(),
        content=content,
        cost_usd=None,
        error=None,
    )


def _strategy(day: date, items: list[Item], now: datetime) -> StrategyRun:
    ids = [item.id for item in items]
    personas = []
    for index, persona in enumerate(PERSONAS):
        if index % 3 == 0:
            personas.append(
                {
                    "key": persona.key,
                    "status": "insight",
                    "headline": "온디바이스 AI 일정과 폴더블 대응 재점검",
                    "insight": "경쟁사 폴더블 진입과 NPU 경쟁을 함께 고려해야 한다.",
                    "actions": ["NPU 로드맵 점검", "폴더블 가격 전략 재검토"],
                    "item_ids": ids[0:1] + ids[2:3],
                }
            )
        else:
            personas.append(
                {
                    "key": persona.key,
                    "status": "no_signal",
                    "headline": "",
                    "insight": "",
                    "actions": [],
                    "item_ids": [],
                }
            )
    claim = lambda cid, text_, refs: {"id": cid, "text": text_, "item_ids": refs}  # noqa: E731
    report = {
        "summary": "모바일 AI와 폴더블 폼팩터에서 동시 대응이 필요하다.",
        "businesses": [
            {
                "business": "mx",
                "summary": "NPU·폴더블 동시 대응",
                "claims": [claim("mx-1", "NPU 성능 우위를 마케팅 핵심으로", ids[0:1] + ids[4:5])],
            }
        ],
        "roadmap": [
            {
                **claim("roadmap-1", "1년: 온디바이스 LLM 기본 탑재", ids[4:5] + ids[6:7]),
                "horizon": "1y",
            },
            {
                **claim("roadmap-2", "3년: 폴더블 라인업 가격대 확장", ids[0:1] + ids[2:3]),
                "horizon": "3y",
            },
        ],
        "opportunities": [
            claim("opp-1", "마이크로 RGB로 프리미엄 TV 수요 선점", ids[1:2] + ids[7:8])
        ],
        "risks": [claim("risk-1", "애플 폴더블 진입으로 점유율 압박", ids[2:3] + ids[0:1])],
    }
    return StrategyRun(
        briefing_date=day,
        input_hash="fixture",
        status=StrategyStatus.OK,
        personas=personas,
        report=report,
        review={"verdict": "pass", "issues": []},
        dropped_claims=0,
        model="fixture",
        cost_usd=None,
        error=None,
        created_at=now,
    )


def seed(session: Session) -> None:
    sources = {
        key: _source(key, name, track, category, region)
        for key, name, track, category, region in SOURCES
    }
    session.add_all(sources.values())
    session.flush()
    for day in (YESTERDAY, TODAY):
        now = NOW - timedelta(days=(TODAY - day).days)
        items = []
        for index, (key, title, title_ko, summary, field, theme, businesses, impact) in enumerate(
            CARDS
        ):
            source = sources[key]
            url = f"https://{key}.example/{day}/{index}"
            item = Item(
                source_id=source.id,
                track=source.track,
                stable_id=url,
                url=url,
                canonical_url=url,
                title=f"{title} ({day:%m/%d})",
                summary=None,
                body=None,
                content_hash=hashlib.sha256(url.encode()).hexdigest(),
                published_at=now - timedelta(hours=index),
                first_seen_at=now - timedelta(hours=index),
                last_changed_at=now,
            )
            session.add(item)
            session.flush()
            session.add(
                ItemCard(
                    item_id=item.id,
                    status=CardStatus.READY,
                    title_ko=f"{title_ko}" if day == TODAY else f"{title_ko} (전일)",
                    summary_ko=summary,
                    keywords=title_ko.split()[:3],
                    engine="fixture",
                    model="fixture",
                    input_hash=item.content_hash,
                    attempts=1,
                    generated_at=now,
                    field=field,
                    themes=[theme],
                    businesses=businesses,
                    impact=impact,
                    scope="dx",
                    relevance=80 - index,
                    taxonomy_revision=TAXONOMY_REVISION,
                )
            )
            items.append(item)
        session.flush()
        freeze = BriefingFreeze(
            briefing_date=day,
            frozen_at=now,
            candidate_ids=[i.id for i in items],
            taxonomy_revision=TAXONOMY_REVISION,
            config={},
        )
        digest = _digest(day, items, now)
        strategy = _strategy(day, items, now)
        session.add_all([freeze, digest, strategy])
        session.flush()
        gates = [
            {
                "name": "translation",
                "label": "번역",
                "value": 1.0,
                "threshold": 0.98,
                "passed": True,
                "blocking": True,
            }
        ]
        session.add(
            Briefing(
                briefing_date=day,
                version=1,
                status=BriefingStatus.PUBLISHED,
                freeze_id=freeze.id,
                digest_id=digest.id,
                strategy_id=strategy.id,
                input_hash=f"fixture-{day}",
                shortlist=[{"item_id": i.id, "track": i.track.value} for i in items],
                gates=gates,
                published_at=now,
            )
        )
    session.commit()


if __name__ == "__main__":
    database_url = os.environ["DATABASE_URL"]
    _reset(database_url)
    engine = create_engine(database_url)
    with Session(engine) as db:
        from news_insight.technologies.catalog import load_technologies
        from news_insight.technologies.service import seed_registry

        seed_registry(db, load_technologies())
        seed(db)
    print(f"seeded {database_url.rsplit('/', 1)[-1]}: briefings {YESTERDAY}, {TODAY}")
