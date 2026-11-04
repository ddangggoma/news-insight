"""Seed a throwaway E2E database with published briefings and spotlights (fixtures, not news).

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
from news_insight.companies.catalog import Relation
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
from news_insight.spotlight.models import (
    Spotlight,
    SpotlightEntry,
    SpotlightFreeze,
    SpotlightStatus,
)
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

# (source, original title, Korean title, summary, field, theme, signal type, impact)
CARDS: list[tuple[str, str, str, list[str], str, str, str, str]] = [
    (
        "etnews",
        "삼성, 온디바이스 AI 칩 공개",
        "삼성, 차세대 온디바이스 AI 칩 공개",
        ["NPU 성능을 2배로 높였다.", "갤럭시 S30에 처음 탑재된다."],
        "platform_sw",
        "platform_sw__device_os",
        "launch",
        "opportunity",
    ),
    (
        "samsung-newsroom",
        "Samsung unveils Micro RGB TV",
        "삼성, 마이크로 RGB TV 공개",
        ["백라이트 없는 자발광 구조다.", "내년 상반기 출시 예정이다."],
        "display_av",
        "display_av__display_panel",
        "launch",
        "opportunity",
    ),
    (
        "the-verge",
        "Apple foldable iPhone enters production",
        "애플 폴더블 아이폰 양산 돌입",
        ["힌지 공급망이 확정됐다.", "2027년 출시가 유력하다."],
        "platform_sw",
        "platform_sw__device_os",
        "launch",
        "risk",
    ),
    (
        "the-verge",
        "Matter 1.5 adds energy management",
        "매터 1.5, 가전 에너지 관리 기능 추가",
        ["스마트홈 표준에 전력 관리 API가 생겼다."],
        "connectivity",
        "connectivity__short_range_wireless",
        "standard",
        "watch",
    ),
    (
        "arxiv",
        "Quantized LLMs for phones",
        "스마트폰용 4비트 양자화 LLM 기법",
        ["메모리 사용량을 60% 줄였다.", "정확도 손실은 1% 미만이다."],
        "ai",
        "ai__on_device_ai",
        "launch",
        "opportunity",
    ),
    (
        "arxiv",
        "6G semantic communication survey",
        "6G 시맨틱 통신 연구 동향 서베이",
        ["표준화 일정과 핵심 과제를 정리했다."],
        "connectivity",
        "connectivity__cellular_5g_6g",
        "research",
        "watch",
    ),
    (
        "github",
        "llama.cpp adds NPU backend",
        "llama.cpp, 모바일 NPU 백엔드 추가",
        ["엑시노스와 스냅드래곤 NPU를 지원한다."],
        "platform_sw",
        "platform_sw__developer_tools",
        "launch",
        "opportunity",
    ),
    (
        "hn",
        "Discussion: smart TV ads backlash",
        "스마트 TV 광고 강제 노출에 개발자 반발",
        ["플랫폼 광고 정책에 대한 비판이 커졌다."],
        "platform_sw",
        "platform_sw__device_os",
        "launch",
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
        "fields": [
            {
                "field": "ai",
                "summary": "NPU·폴더블 동시 대응",
                "claims": [claim("ai-1", "NPU 성능 우위를 마케팅 핵심으로", ids[0:1] + ids[4:5])],
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


# (section, rank, stat_rank, key, card index, title, product_name, rank_note, fallback)
# Yesterday's list shares keys with today's so the page shows NEW, up and down badges.
SPOTLIGHT_TODAY: list[tuple[str, int, int, str, int, str, str | None, str | None, bool]] = [
    (
        "news",
        1,
        2,
        "n-chip",
        0,
        "온디바이스 칩 소식이 가장 크게 번졌다",
        None,
        "파급력이 커서 통계보다 올림",
        False,
    ),
    ("news", 2, 1, "n-fold", 2, "폴더블 양산 소식이 뒤를 이었다", None, None, False),
    ("news", 3, 3, "n-matter", 3, "스마트홈 표준 갱신 소식", None, None, True),
    ("product", 1, 1, "p-tv", 1, "마이크로 RGB TV 공개", "Micro RGB TV", None, False),
    (
        "ai",
        1,
        1,
        "ai:phone-llm",
        4,
        "스마트폰용 4비트 LLM이 주목받았다",
        "Phone LLM 4bit",
        None,
        False,
    ),
    ("oss", 1, 1, "o-llama", 6, "llama.cpp 모바일 NPU 백엔드 추가", None, None, False),
]
# 지속 주목 rows of today (B3), same tuple shape
SPOTLIGHT_SUSTAINED: list[tuple[str, int, int, str, int, str, str | None, str | None, bool]] = [
    (
        "news",
        1,
        1,
        "n-rgb-week",
        1,
        "마이크로 RGB 패널 경쟁이 일주일째 이어졌다",
        None,
        None,
        False,
    ),
]
# Opus's insight tags and the server's signals, by key
SPOTLIGHT_TAGS: dict[str, tuple[list[str], list[str]]] = {
    "n-chip": (["첫 공개", "NPU 2배"], ["보도 4곳"]),
    "n-rgb-week": (["장기 화제"], ["7일 중 5일"]),
}
SPOTLIGHT_YESTERDAY: list[tuple[str, int, int, str, int, str, str | None, str | None, bool]] = [
    ("news", 1, 1, "n-fold", 2, "폴더블 양산 소식", None, None, False),
    ("news", 2, 2, "n-chip", 0, "온디바이스 칩 소식", None, None, False),
    ("product", 1, 1, "p-tv-old", 1, "전일 제품", "Micro RGB TV", None, False),
]


def _spotlight(
    day: date,
    rows: list[tuple[str, int, int, str, int, str, str | None, str | None, bool]],
    items: list[Item],
    now: datetime,
    freeze_id: int,
) -> tuple[Spotlight, list[SpotlightEntry]]:
    spotlight = Spotlight(
        spotlight_date=day,
        status=SpotlightStatus.PUBLISHED,
        model="fixture",
        cost_usd=None,
        headline=(
            "오늘은 온디바이스 AI 칩과 폴더블 소식이 화제를 주도했다"
            if day == TODAY
            else "전일에는 폴더블 양산 소식이 화제였다"
        ),
        benchmark_note="",
        freeze_id=freeze_id,
        error=None,
        generated_at=now,
    )
    groups = [("now", rows)] + ([("sustained", SPOTLIGHT_SUSTAINED)] if day == TODAY else [])
    entries = [
        SpotlightEntry(
            group=group,
            tags=SPOTLIGHT_TAGS.get(key, ([], []))[0] if day == TODAY else [],
            signals=SPOTLIGHT_TAGS.get(key, ([], []))[1] if day == TODAY else [],
            field=CARDS[card][4],
            section=section,
            rank=rank,
            stat_rank=stat_rank,
            key=key,
            item_ids=[items[card].id],
            title_ko=title,
            product_name=product,
            summary=f"{title} 요약",
            why_hot="" if fallback else f"{title}: 여러 매체가 동시에 보도",
            rank_note=note,
            metrics={"source_count": 5 - rank},
            fallback=fallback,
        )
        for group, listed in groups
        for section, rank, stat_rank, key, card, title, product, note, fallback in listed
    ]
    return spotlight, entries


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
        for index, (key, title, title_ko, summary, field, theme, signal, impact) in enumerate(
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
                    signal_type=signal,
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
        # the 주목 받는 page (plan 18): a published list per day, built on the day's items
        spotlight_freeze = SpotlightFreeze(spotlight_date=day, frozen_at=now, candidates={})
        session.add(spotlight_freeze)
        session.flush()
        spotlight, entries = _spotlight(
            day,
            SPOTLIGHT_TODAY if day == TODAY else SPOTLIGHT_YESTERDAY,
            items,
            now,
            spotlight_freeze.id,
        )
        session.add(spotlight)
        session.flush()
        for entry in entries:
            entry.spotlight_id = spotlight.id
        session.add_all(entries)
    session.commit()


# 연구·특허 menus (plan 19): papers and patents spread over the last 12 weeks, older than the
# explore feed's default week so the other reader pages see the same items as before, and the
# daily stats rebuilt from them. (field, theme, days ago, company keys, institutions, countries)
E2E_COMPANIES = [
    ("samsung", "Samsung Electronics", "삼성전자", Relation.SELF),
    ("lg-electronics", "LG Electronics", "LG전자", Relation.COMPETITOR),
    ("sony", "Sony", "소니", Relation.PEER),
]
SAMSUNG = {
    "name": "Samsung Electronics",
    "type": "company",
    "country": "KR",
    "company_key": "samsung",
}
LG = {"name": "LG Electronics", "type": "company", "country": "KR", "company_key": "lg-electronics"}
KAIST = {"name": "KAIST", "type": "education", "country": "KR"}
MIT = {"name": "Massachusetts Institute of Technology", "type": "education", "country": "US"}
TSINGHUA = {"name": "Tsinghua University", "type": "education", "country": "CN"}
PAPERS: list[tuple[str, str, int, list[dict[str, Any]]]] = [
    ("ai", "ai__foundation_models", 8, [SAMSUNG, KAIST]),
    ("ai", "ai__ai_agents", 10, [MIT]),
    ("ai", "ai__multimodal_perception", 12, [LG, KAIST]),
    ("ai", "ai__foundation_models", 15, [TSINGHUA]),
    ("ai", "ai__ai_agents", 20, [SAMSUNG]),
    ("semis", "semis__ap_soc_npu", 9, [SAMSUNG, MIT]),
    ("semis", "semis__memory_storage", 25, [TSINGHUA]),
    ("connectivity", "connectivity__cellular_5g_6g", 14, [KAIST]),
    ("display_av", "display_av__display_panel", 18, [LG]),
    ("ai", "ai__foundation_models", 40, [MIT]),
    ("semis", "semis__ap_soc_npu", 45, [SAMSUNG]),
    ("connectivity", "connectivity__ran_core", 50, [TSINGHUA]),
    ("display_av", "display_av__display_panel", 60, [KAIST]),
    ("ai", "ai__ai_agents", 70, [MIT]),
    ("semis", "semis__memory_storage", 75, [LG]),
]
# (field, theme, days ago, company keys, applicants, office, source, publication number)
PATENTS: list[tuple[str, str, int, list[str], list[str], str, str, str | None]] = [
    (
        "display_av",
        "display_av__display_panel",
        8,
        ["samsung"],
        ["Samsung Display"],
        "KR",
        "news",
        None,
    ),
    (
        "display_av",
        "display_av__display_panel",
        11,
        ["lg-electronics"],
        ["LG Electronics Inc."],
        "EP",
        "eps",
        "EP4815726",
    ),
    (
        "ai",
        "ai__multimodal_perception",
        13,
        ["samsung"],
        ["Samsung Electronics Co., Ltd."],
        "US",
        "news",
        None,
    ),
    (
        "connectivity",
        "connectivity__cellular_5g_6g",
        16,
        ["lg-electronics"],
        ["LG Electronics Inc."],
        "EP",
        "eps",
        "EP4820011",
    ),
    (
        "semis",
        "semis__memory_storage",
        22,
        ["sony"],
        ["Sony Group Corporation"],
        "EP",
        "eps",
        "EP4801234",
    ),
    (
        "display_av",
        "display_av__camera_imaging",
        27,
        ["sony"],
        ["Sony Semiconductor Solutions"],
        "EP",
        "eps",
        "EP4799999",
    ),
    (
        "display_av",
        "display_av__display_panel",
        38,
        ["samsung"],
        ["Samsung Display"],
        "KR",
        "news",
        None,
    ),
    ("ai", "ai__ai_agents", 55, ["lg-electronics"], ["LG Electronics Inc."], "US", "news", None),
    (
        "semis",
        "semis__ap_soc_npu",
        66,
        ["samsung"],
        ["Samsung Electronics Co., Ltd."],
        "EP",
        "eps",
        "EP4700001",
    ),
]


def _domain_item(
    session: Session,
    source: Source,
    slug: str,
    title: str,
    title_ko: str,
    field: str,
    theme: str,
    signal: str,
    when: datetime,
) -> Item:
    url = f"https://{source.key}.example/{slug}"
    item = Item(
        source_id=source.id,
        track=source.track,
        stable_id=url,
        url=url,
        canonical_url=url,
        title=title,
        summary=None,
        body=None,
        content_hash=hashlib.sha256(url.encode()).hexdigest(),
        published_at=when,
        first_seen_at=when,
        last_changed_at=when,
    )
    session.add(item)
    session.flush()
    session.add(
        ItemCard(
            item_id=item.id,
            status=CardStatus.READY,
            title_ko=title_ko,
            summary_ko=[f"{title_ko}에 관한 요약이다."],
            keywords=title_ko.split()[:3],
            engine="fixture",
            model="fixture",
            input_hash=item.content_hash,
            attempts=1,
            generated_at=when,
            field=field,
            themes=[theme],
            signal_type=signal,
            impact="watch",
            scope="dx",
            relevance=60,
            taxonomy_revision=TAXONOMY_REVISION,
        )
    )
    return item


def seed_domains(session: Session) -> None:
    from news_insight.companies.models import Company
    from news_insight.insights.stats import recompute_days
    from news_insight.patents.models import PatentMeta, PatentSource
    from news_insight.research.models import EnrichStatus, ResearchMeta

    for key, name, name_ko, relation in E2E_COMPANIES:
        session.add(Company(key=key, name=name, name_ko=name_ko, relation=relation))
    arxiv = session.query(Source).filter_by(key="arxiv").one()
    office = _source("epo-pub", "EPO 공보", Track.RESEARCH_IP, "patent_office", Region.GLOBAL_EN)
    news = session.query(Source).filter_by(key="etnews").one()
    session.add(office)
    session.flush()
    for index, (field, theme, back, institutions) in enumerate(PAPERS):
        when = NOW - timedelta(days=back, hours=index)
        label = theme.split("__", 1)[1].replace("_", " ")
        item = _domain_item(
            session,
            arxiv,
            f"paper-{index}",
            f"Paper on {label} #{index}",
            f"{label} 연구 {index}",
            field,
            theme,
            "research",
            when,
        )
        companies = [i["company_key"] for i in institutions if i.get("company_key")]
        session.add(
            ResearchMeta(
                item_id=item.id,
                doi=f"10.48550/arXiv.2610.{index:05d}",
                venue="NeurIPS" if index % 2 else "arXiv",
                institutions=institutions,
                countries=sorted({i["country"] for i in institutions}),
                company_keys=companies,
                has_company=bool(companies),
                cited_by=index * 3,
                status=EnrichStatus.OK,
                enriched_at=NOW,
            )
        )
    for index, (field, theme, back, keys, applicants, office_code, kind, number) in enumerate(
        PATENTS
    ):
        when = NOW - timedelta(days=back, hours=index)
        label = theme.split("__", 1)[1].replace("_", " ")
        source = office if kind == "eps" else news
        item = _domain_item(
            session,
            source,
            f"patent-{index}",
            f"Patent on {label} #{index}",
            f"{label} 특허 {index}",
            field,
            theme,
            "ip",
            when,
        )
        session.add(
            PatentMeta(
                item_id=item.id,
                publication_number=number,
                kind="A1" if number else None,
                office=office_code,
                applicants=applicants,
                company_keys=keys,
                field=field,
                fields=[field],
                source=PatentSource(kind),
                indexed_at=NOW,
            )
        )
    session.flush()
    recompute_days(session, [TODAY - timedelta(days=back) for back in range(1, 91)])
    session.commit()


# Login fixtures (plan 14); apps/web/e2e/accounts.ts has the same names and password.
E2E_PASSWORD = "e2e-plum-orbit-4417"


def seed_accounts(session: Session) -> None:
    from news_insight.auth.accounts import Client, approve, create_admin, register

    admin = create_admin(
        session, username="e2e.admin", password=E2E_PASSWORD, name="관리자", now=NOW
    )
    reader = register(
        session,
        username="e2e.reader",
        password=E2E_PASSWORD,
        name="독자",
        now=NOW,
        client=Client(),
    )
    approve(session, admin, reader.id, now=NOW, client=Client())
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
        seed_domains(db)
        seed_accounts(db)
        from news_insight.taxonomy.seed import backfill_labels, seed_taxonomy

        seed_taxonomy(db)  # schemes and labels for the explorer and node filters (plan 15)
        backfill_labels(db)
        db.commit()
        # the explore feed, facets and insights read reader_facts (#135); live rebuilds it every
        # few minutes, but here no scheduler runs, so the view stays as the migration left it: empty
        from news_insight.public.facts import refresh

        refresh(db)
        db.commit()
    print(f"seeded {database_url.rsplit('/', 1)[-1]}: briefings {YESTERDAY}, {TODAY}")
