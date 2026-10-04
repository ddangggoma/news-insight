"""Synthetic radar corpus for UI review: ~40 weeks of classified reports with planted patterns.

Every chart on the radar should find something here, and the patterns are known in advance so a
chart that misses one (or invents one) is easy to spot:

- surges (AI agents, humanoids), first appearances (glass substrate, hybrid bonding, VLA), a
  returning keyword (메타버스), falling themes (XR, 6G)
- research-led themes (Embodied AI, PQC), a research → market shift (OLED·MicroLED), a hype gap
  (robotaxi chatter without research), a vendor-driven spike (One UI from one newsroom)
- regional specialization (KR memory/display/AI law, JP robotics, CN batteries, EU AI Act), a
  Korean gap (Claude Code, WASM) and a Korean lag (VLA ~10 days late)
- paper → repo → community → news chains through shared arXiv ids, star/point growth that is
  strong for coding agents and absent for XR, two event days and quieter weekends
- cross-category reports (on-device AI × chips, Embodied AI × robotics, PQC × quantum)
- synonyms the alias table must merge (대형언어모델/LLM, AI Agent/AI 에이전트)

Usage (never on a real database; the name must contain "demo"):
    createdb news_insight_demo
    DATABASE_URL=postgresql+psycopg://news:…@localhost:8720/news_insight_demo \\
        uv run alembic upgrade head && uv run python scripts/radar_demo_seed.py
"""

import math
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import insert, select, text
from sqlalchemy.engine import make_url

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.config import get_settings
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.db import session_scope
from news_insight.public.periods import KST
from news_insight.sources.enums import (
    AccessMethod,
    PollClass,
    Region,
    SourceStatus,
    StorageRight,
    ValidationStage,
)
from news_insight.sources.enums import Track as T
from news_insight.sources.models import Source
from news_insight.stories.models import ItemRef, Relation, Story, StoryItem
from news_insight.taxonomy.catalog import TAXONOMY_REVISION

rng = random.Random(20261004)
NOW = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
DAYS = 280
KR, EN, JP, CN, EU = Region.KR, Region.GLOBAL_EN, Region.JP, Region.GREATER_CHINA, Region.EU_OTHER


def kst_date(day: int) -> date:
    """Calendar date (KST) of simulation day `day`; DAYS - 1 is today."""
    return NOW.astimezone(KST).date() - timedelta(days=DAYS - 1 - day)


# key, name, track, region, category
SOURCES = [
    ("etnews", "전자신문", T.NEWS, KR, "independent_media"),
    ("thelec", "디일렉", T.NEWS, KR, "independent_media"),
    ("zdnet-kr", "지디넷코리아", T.NEWS, KR, "independent_media"),
    ("samsung-newsroom", "Samsung Newsroom", T.NEWS, KR, "official_vendor"),
    ("verge", "The Verge", T.NEWS, EN, "independent_media"),
    ("techcrunch", "TechCrunch", T.NEWS, EN, "independent_media"),
    ("ars", "Ars Technica", T.NEWS, EN, "independent_media"),
    ("ieee", "IEEE Spectrum", T.NEWS, EN, "independent_media"),
    ("google-blog", "Google Blog", T.NEWS, EN, "official_vendor"),
    ("nikkei-xtech", "日経クロステック", T.NEWS, JP, "independent_media"),
    ("itmedia", "ITmedia", T.NEWS, JP, "independent_media"),
    ("36kr", "36Kr", T.NEWS, CN, "independent_media"),
    ("ithome", "iThome", T.NEWS, CN, "independent_media"),
    ("heise", "heise online", T.NEWS, EU, "independent_media"),
    ("euractiv", "Euractiv", T.NEWS, EU, "independent_media"),
    ("geeknews", "GeekNews", T.COMMUNITY, KR, "dev_forum"),
    ("clien", "클리앙 모두의공원", T.COMMUNITY, KR, "dev_forum"),
    ("hn", "Hacker News", T.COMMUNITY, EN, "dev_forum"),
    ("reddit-ml", "r/MachineLearning", T.COMMUNITY, EN, "open_social"),
    ("qiita", "Qiita", T.COMMUNITY, JP, "dev_forum"),
    ("v2ex", "V2EX", T.COMMUNITY, CN, "dev_forum"),
    ("arxiv", "arXiv", T.RESEARCH_IP, EN, "academic_paper"),
    ("ieee-xplore", "IEEE Xplore", T.RESEARCH_IP, EN, "academic_index"),
    ("kipris", "KIPRIS 특허", T.RESEARCH_IP, KR, "ip_office"),
    ("jstage", "J-STAGE", T.RESEARCH_IP, JP, "academic_index"),
    ("github", "GitHub Trending", T.OSS, EN, "oss_trend"),
    ("github-kr", "GitHub · 국내 저장소", T.OSS, KR, "oss_trend"),
    ("huggingface", "Hugging Face", T.OSS, EN, "oss_release"),
]

TRACKS = (T.NEWS, T.COMMUNITY, T.RESEARCH_IP, T.OSS)
BASE_REGIONS = {KR: 0.25, EN: 0.5, JP: 0.08, CN: 0.1, EU: 0.07}


@dataclass
class Kw:
    label: str
    weight: float = 1.0
    start: int = 0  # first simulation day it may appear
    stop: int = DAYS  # last day (exclusive)
    kr_from: int = 0  # Korean sources only from this day on
    kr: bool = True  # False: never in Korean sources
    variants: tuple[str, ...] = ()  # other spellings the alias table should merge
    surge_from: int = DAYS  # weight × 4 from this day on


@dataclass
class Theme:
    key: str
    base: float  # reports per week before profile and events
    profile: str
    tracks_from: tuple[float, float, float, float]  # news, community, research, oss
    tracks_to: tuple[float, float, float, float] | None = None
    shift_from: int = 0  # the move from tracks_from to tracks_to starts on this day (over 14 days)
    regions: dict[Region, float] = field(default_factory=dict)
    impacts: tuple[float, float, float] = (0.45, 0.2, 0.35)  # opportunity, risk, watch
    keywords: list[Kw] = field(default_factory=list)
    also: tuple[tuple[str, float], ...] = ()  # (other theme, probability) on the same card
    official: float = 0.0  # share of news reports from vendor newsrooms
    stars: float = 1.0  # engagement multiplier for oss/community reports
    chains: int = 0  # paper → repo → community → news chains over the simulation


THEMES = [
    Theme(
        "ai__ai_agents",
        14,
        "surge",
        (5, 4, 2, 3),
        impacts=(0.65, 0.15, 0.2),
        keywords=[
            Kw("AI 에이전트", 3, variants=("AI Agent", "AI에이전트")),
            Kw("MCP", 2),
            Kw("에이전트 OS", 1.5, surge_from=DAYS - 14),
            Kw("컴퓨터 사용 에이전트"),
            Kw("A2A 프로토콜", 1, start=DAYS - 60),
        ],
        also=(
            ("platform_sw__developer_tools", 0.15),
            ("ai__on_device_ai", 0.15),
        ),
        stars=2.5,
        chains=30,
    ),
    Theme(
        "ai__foundation_models",
        20,
        "flat",
        (5, 3, 3, 2),
        keywords=[
            Kw("LLM", 3, variants=("대형언어모델", "거대언어모델", "Large Language Model")),
            Kw("추론 모델", 2),
            Kw("Gemini"),
            Kw("GPT"),
            Kw("오픈 웨이트"),
        ],
        stars=1.5,
        chains=18,
    ),
    Theme(
        "ai__on_device_ai",
        9,
        "grow",
        (3, 2, 3, 3),
        impacts=(0.6, 0.1, 0.3),
        keywords=[
            Kw("온디바이스 AI", 3, variants=("On-device AI", "온디바이스AI")),
            Kw("NPU", 2),
            Kw("소형 언어모델", variants=("SLM",)),
            Kw("양자화"),
        ],
        also=(("semis__ap_soc_npu", 0.35), ("platform_sw__device_os", 0.2)),
        chains=15,
    ),
    Theme(
        "ai__multimodal_perception",
        8,
        "flat",
        (3, 2, 3, 2),
        keywords=[Kw("비전 언어 모델"), Kw("음성 AI"), Kw("월드 모델")],
    ),
    Theme(
        "cloud_data__data_ml_platform",
        5,
        "flat",
        (2, 2, 1, 4),
        keywords=[Kw("벡터 DB"), Kw("RAG", 2, variants=("검색증강생성",))],
        stars=1.5,
    ),
    Theme(
        "semis__memory_storage",
        11,
        "grow",
        (6, 1, 2, 1),
        regions={KR: 0.55, EN: 0.3, JP: 0.05, CN: 0.07, EU: 0.03},
        impacts=(0.5, 0.3, 0.2),
        keywords=[Kw("HBM4", 3), Kw("CXL"), Kw("LPDDR6"), Kw("PIM")],
        also=(("cloud_data__infra_ops", 0.15),),
    ),
    Theme(
        "semis__packaging_chiplet",
        5,
        "new",
        (3, 0, 4, 1),
        regions={KR: 0.5, EN: 0.3, JP: 0.1, CN: 0.07, EU: 0.03},
        keywords=[
            Kw("유리기판", 2, start=DAYS - 21),
            Kw("하이브리드 본딩", 2, start=DAYS - 18),
            Kw("칩렛", variants=("Chiplet",)),
        ],
    ),
    Theme(
        "semis__ap_soc_npu",
        6,
        "flat",
        (4, 1, 2, 1),
        keywords=[Kw("엑시노스"), Kw("2나노"), Kw("RISC-V")],
    ),
    Theme(
        "platform_sw__device_os",
        11,
        "wave",
        (7, 3, 0, 0),
        official=0.25,
        keywords=[Kw("갤럭시", 2), Kw("폴더블"), Kw("아이폰"), Kw("트라이폴드")],
        also=(("ai__on_device_ai", 0.3),),
    ),
    Theme(
        "platform_sw__device_os",
        6,
        "spike",
        (5, 2, 0, 1),
        official=0.75,
        keywords=[Kw("One UI 9", 3, start=DAYS - 10), Kw("Android 17"), Kw("Wear OS")],
    ),
    Theme(
        "health_tech__biosensing",
        6,
        "grow",
        (3, 2, 2, 1),
        keywords=[Kw("스마트링"), Kw("비침습 혈당"), Kw("갤럭시 워치")],
    ),
    Theme(
        "display_av__display_panel",
        7,
        "flat",
        (2, 1, 5, 1),
        tracks_to=(7, 2, 1, 0),
        shift_from=DAYS - 16,
        regions={KR: 0.5, EN: 0.25, JP: 0.1, CN: 0.12, EU: 0.03},
        keywords=[Kw("OLED", 2), Kw("마이크로LED", variants=("MicroLED",)), Kw("QD-OLED")],
    ),
    Theme(
        "display_av__xr_spatial",
        7,
        "fall",
        (5, 3, 1, 1),
        stars=0.1,
        keywords=[
            Kw("XR 헤드셋"),
            Kw("스마트 글래스"),
            Kw("Vision Pro"),
            Kw("메타버스", 1.5, stop=30),
            Kw("메타버스", 6, start=DAYS - 6),
        ],
    ),
    Theme(
        "connectivity__cellular_5g_6g",
        7,
        "fall",
        (3, 1, 3, 0),
        impacts=(0.3, 0.2, 0.5),
        keywords=[Kw("6G", 2), Kw("5G-Advanced"), Kw("AI-RAN")],
    ),
    Theme(
        "connectivity__satellite_ntn",
        4,
        "grow",
        (2, 1, 2, 0),
        keywords=[Kw("NTN", variants=("비지상 네트워크",)), Kw("위성 직접통신")],
    ),
    Theme(
        "cloud_data__infra_ops",
        6,
        "flat",
        (1, 3, 0, 4),
        keywords=[Kw("Kubernetes"), Kw("WASM", 2, kr=False), Kw("eBPF", kr=False)],
        stars=1.5,
    ),
    Theme(
        "cloud_data__infra_ops",
        4,
        "grow",
        (2, 1, 1, 1),
        impacts=(0.3, 0.45, 0.25),
        keywords=[Kw("데이터센터 전력"), Kw("액침 냉각")],
    ),
    Theme(
        "platform_sw__developer_tools",
        6,
        "grow",
        (1, 4, 0, 5),
        stars=6,
        keywords=[
            Kw("코딩 에이전트", 2),
            Kw("Claude Code", 2, kr=False),
            Kw("바이브 코딩", variants=("Vibe Coding",)),
        ],
        chains=12,
    ),
    Theme(
        "platform_sw__developer_tools",
        4,
        "flat",
        (1, 3, 1, 2),
        keywords=[Kw("Rust"), Kw("Mojo")],
    ),
    Theme(
        "security__software_supply_chain",
        4,
        "flat",
        (1, 2, 1, 2),
        impacts=(0.15, 0.6, 0.25),
        keywords=[Kw("SBOM"), Kw("xz 백도어")],
    ),
    Theme(
        "security__privacy_crypto",
        4,
        "new",
        (1, 1, 4, 2),
        impacts=(0.3, 0.4, 0.3),
        keywords=[Kw("포스트양자 암호", 2, start=DAYS - 25, variants=("PQC",)), Kw("동형암호")],
        chains=12,
    ),
    Theme(
        "security__device_security",
        5,
        "wave",
        (3, 2, 2, 0),
        impacts=(0.2, 0.55, 0.25),
        keywords=[Kw("Knox"), Kw("TEE")],
    ),
    Theme(
        "robotics_mobility__humanoid_embodied",
        6,
        "surge",
        (4, 2, 2, 2),
        regions={KR: 0.2, EN: 0.4, JP: 0.25, CN: 0.12, EU: 0.03},
        keywords=[Kw("휴머노이드", 2, variants=("Humanoid",)), Kw("가정용 로봇"), Kw("Optimus")],
        also=(("robotics_mobility__humanoid_embodied", 0.3),),
        stars=1.5,
    ),
    Theme(
        "robotics_mobility__humanoid_embodied",
        4,
        "grow",
        (1, 1, 5, 4),
        regions={KR: 0.22, EN: 0.5, JP: 0.18, CN: 0.08, EU: 0.02},
        keywords=[
            Kw("VLA 모델", 2, start=DAYS - 40, kr_from=DAYS - 30),
            Kw("로봇 파운데이션 모델"),
            Kw("시뮬레이션 학습"),
        ],
        also=(("ai__multimodal_perception", 0.3),),
        stars=3,
        chains=24,
    ),
    Theme(
        "robotics_mobility__autonomous_driving",
        6,
        "hype",
        (4, 2, 1, 1),
        keywords=[
            Kw("로보택시", 2, surge_from=DAYS - 8),
            Kw("SDV"),
            Kw("자율주행 레벨3", variants=("자율 주행 레벨3",)),
        ],
        also=(("ai__multimodal_perception", 0.2),),
    ),
    Theme(
        "manufacturing__logistics_automation",
        4,
        "flat",
        (4, 0, 1, 0),
        impacts=(0.15, 0.6, 0.25),
        keywords=[Kw("공급망 재편"), Kw("희토류")],
    ),
    Theme(
        "platform_sw__app_ecosystem",
        8,
        "wave",
        (7, 2, 0, 0),
        keywords=[Kw("인수합병"), Kw("파트너십")],
    ),
    Theme(
        "ai__ai_safety_eval",
        6,
        "grow",
        (4, 2, 2, 0),
        regions={KR: 0.3, EN: 0.3, JP: 0.05, CN: 0.05, EU: 0.3},
        impacts=(0.15, 0.55, 0.3),
        keywords=[Kw("EU AI Act", 2), Kw("AI 기본법", 2)],
    ),
    Theme(
        "semis__ap_soc_npu",
        5,
        "flat",
        (5, 1, 0, 0),
        impacts=(0.1, 0.7, 0.2),
        keywords=[Kw("수출통제", 2), Kw("관세")],
    ),
    Theme(
        "frontier__quantum",
        3,
        "grow",
        (1, 1, 3, 1),
        keywords=[Kw("양자컴퓨터", variants=("양자 컴퓨팅",)), Kw("양자 오류정정")],
        chains=9,
    ),
    Theme(
        "energy__battery_charging",
        4,
        "flat",
        (3, 1, 2, 0),
        regions={KR: 0.25, EN: 0.25, JP: 0.1, CN: 0.35, EU: 0.05},
        keywords=[Kw("전고체 배터리"), Kw("실리콘 음극재")],
    ),
]
# PQC meets quantum only in the current week: a brand-new cross-category link
NEW_LINK = (
    "security__privacy_crypto",
    "frontier__quantum",
    DAYS - 6,
)


def weekday_near(days_ago: int) -> int:
    """Simulation day about `days_ago` days back, moved to the nearest earlier Tuesday–Thursday:
    launch events and conferences rarely land on weekends."""
    day = DAYS - 1 - days_ago
    while kst_date(day).weekday() not in (1, 2, 3):
        day -= 1
    return day


EVENTS = {  # day → (boost per theme, extra official share)
    weekday_near(8): (
        {
            "platform_sw__device_os": 14,
            "health_tech__biosensing": 8,
            "ai__on_device_ai": 6,
        },
        0.3,
    ),
    DAYS - 3: ({"display_av__xr_spatial": 12}, 0.0),  # 메타버스 comes back
    weekday_near(35): (
        {
            "ai__ai_agents": 8,
            "ai__foundation_models": 6,
            "platform_sw__developer_tools": 8,
        },
        0.1,
    ),
}


def weight(profile: str, day: int) -> float:
    x = day / (DAYS - 1)
    last = DAYS - day
    return {
        "flat": 1.0,
        "grow": 0.5 + 1.0 * x,
        "surge": 0.8 if last > 14 else (2.2 if last > 7 else 3.6),
        "new": 0.0 if last > 25 else 1.6,
        "fall": 1.7 - 1.4 * x,
        "wave": 1.0 + 0.45 * math.sin(day / 9),
        "spike": 0.8 if last > 10 else 3.0,
        "hype": 1.0 if last > 8 else 2.6,
    }[profile]


def poisson(lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def day_time(day: int) -> datetime:
    """A moment inside the KST calendar day of `day`, never in the future."""
    start = datetime.combine(kst_date(day), datetime.min.time(), tzinfo=KST)
    return min(start + timedelta(hours=rng.uniform(7, 23)), NOW - timedelta(minutes=5))


@dataclass
class Plan:
    day: int
    at: datetime
    theme: Theme
    track: T
    source: str
    keywords: list[str]
    themes: list[str]
    ref: str | None = None


def pick_source(track: T, region: Region, official: bool) -> str:
    pool = [s for s in SOURCES if s[2] == track and s[3] == region]
    if track == T.NEWS:
        vendor = [s for s in pool if s[4] == "official_vendor"]
        pool = (
            vendor
            if official and vendor
            else [s for s in pool if s[4] != "official_vendor"] or pool
        )
    pool = (
        pool
        or [s for s in SOURCES if s[2] == track and s[3] == EN]
        or [s for s in SOURCES if s[2] == track]
    )
    return rng.choice(pool)[0]


def keywords_for(theme: Theme, day: int, region: Region) -> list[str]:
    usable = [
        k
        for k in theme.keywords
        if k.start <= day < k.stop and (region != KR or (k.kr and day >= k.kr_from))
    ]
    if not usable:
        return []
    weights = [k.weight * (4 if day >= k.surge_from else 1) for k in usable]
    chosen: list[Kw] = []
    for _ in range(rng.choice([1, 2, 2, 3])):
        k = rng.choices(usable, weights)[0]
        if k not in chosen:
            chosen.append(k)
    return [
        rng.choice((k.label, *k.variants)) if k.variants and rng.random() < 0.3 else k.label
        for k in chosen
    ]


def plan_items() -> list[Plan]:
    plans: list[Plan] = []
    for day in range(DAYS):
        weekday = kst_date(day).weekday()
        season = 0.45 if weekday >= 5 else 1.0
        boosts, official_extra = EVENTS.get(day, ({}, 0.0))
        for theme in THEMES:
            lam = theme.base / 7 * weight(theme.profile, day) * season * boosts.get(theme.key, 1)
            if day == DAYS - 1:
                lam *= 0.5  # today is half over
            for _ in range(poisson(lam)):
                x = min(max((day - theme.shift_from) / 14, 0.0), 1.0)
                mix = (
                    theme.tracks_from
                    if theme.tracks_to is None
                    else tuple(
                        a * (1 - x) + b * x
                        for a, b in zip(theme.tracks_from, theme.tracks_to, strict=True)
                    )
                )
                if theme.profile == "hype" and DAYS - day <= 8:
                    mix = (mix[0] * 2.5, mix[1] * 2.5, mix[2] * 0.3, mix[3] * 0.3)
                track = rng.choices(TRACKS, mix)[0]
                regions = theme.regions or BASE_REGIONS
                region = rng.choices(list(regions), list(regions.values()))[0]
                official = rng.random() < theme.official + official_extra
                if theme.official >= 0.5 and DAYS - day <= 10 and track == T.NEWS:
                    region = KR  # the One UI spike comes from one Korean newsroom
                words = keywords_for(theme, day, region)
                if not words:
                    continue
                themes = [theme.key]
                for other, chance in theme.also:
                    if rng.random() < chance:
                        themes.append(other)
                if theme.key == NEW_LINK[0] and day >= NEW_LINK[2] and rng.random() < 0.6:
                    themes.append(NEW_LINK[1])
                plans.append(
                    Plan(
                        day,
                        day_time(day),
                        theme,
                        track,
                        pick_source(track, region, official),
                        words,
                        themes,
                    )
                )
    for theme in THEMES:
        for _ in range(theme.chains):
            start = rng.randint(DAYS - 120, DAYS - 3)
            ref = f"arxiv:2610.{rng.randint(10000, 99999)}"
            words = keywords_for(theme, start, EN) or [theme.keywords[0].label]
            steps = [
                (T.RESEARCH_IP, 0),
                (T.OSS, rng.uniform(1, 3)),
                (T.COMMUNITY, rng.uniform(3, 6)),
                (T.NEWS, rng.uniform(6, 12)),
            ]
            for track, delay in steps[: rng.choice([2, 3, 4, 4])]:
                at = day_time(start) + timedelta(days=delay, hours=rng.uniform(0, 6))
                if at >= NOW:
                    break
                region = EN if track != T.NEWS else rng.choice([EN, EN, KR, JP])
                plans.append(
                    Plan(
                        start,
                        at,
                        theme,
                        track,
                        pick_source(track, region, False),
                        words,
                        [theme.key],
                        ref,
                    )
                )
    return plans


SIGNALS = ["research", "launch", "market", "ecosystem", "standard", "regulation"]


def main() -> None:
    database = make_url(get_settings().database_url).database or ""
    if "demo" not in database:
        raise SystemExit(
            f"refusing to seed '{database}': use a database whose name contains 'demo'"
        )
    plans = plan_items()
    with session_scope() as session:
        session.execute(text("TRUNCATE sources RESTART IDENTITY CASCADE"))
        sources = {
            key: Source(
                key=key,
                name=name,
                track=track,
                region=region,
                category=category,
                access_method=AccessMethod.FEED,
                endpoint_url=f"https://{key}.example/feed",
                official_domain=f"{key}.example",
                operator=name,
                language="ko" if region == KR else "en",
                poll_class=PollClass.NEWS,
                dx_relevance="demo",
                terms_url=f"https://{key}.example/terms",
                storage_right=StorageRight.METADATA_ONLY,
                config={},
                validation_stage=ValidationStage.V6,
                status=SourceStatus.ACTIVE,
            )
            for key, name, track, region, category in SOURCES
        }
        session.add_all(sources.values())
        session.flush()
        for n, plan in enumerate(plans):
            verb = ["공개", "연구", "출시", "분석", "논의", "도입"][n % 6]
            topic = plan.theme.key.split("__")[1].replace("_", " ")
            title = f"{plan.keywords[0]} {verb} — {topic} #{n}"
            ingest_items(
                session,
                sources[plan.source],
                [
                    RawItem(
                        stable_id=f"demo-{n}", url=f"https://{plan.source}.example/{n}", title=title
                    )
                ],
                fetch_run=None,
                now=plan.at,
                canary=False,
            )
        session.flush()
        items = {i.stable_id: i for i in session.scalars(select(Item))}
        snapshots = []
        for n, plan in enumerate(plans):
            item = items[f"demo-{n}"]
            field_key = plan.theme.key.split("__")[0]
            opportunity, risk, _ = plan.theme.impacts
            r = rng.random()
            session.add(
                ItemCard(
                    item_id=item.id,
                    status=CardStatus.READY,
                    title_ko=item.title,
                    summary_ko=[
                        f"{plan.keywords[0]} 관련 요약 문장입니다.",
                        "두 번째 요약 문장입니다.",
                    ],
                    keywords=plan.keywords,
                    engine="demo",
                    model="demo",
                    input_hash=item.content_hash,
                    attempts=0,
                    generated_at=item.first_seen_at,
                    field=field_key,
                    themes=plan.themes,
                    signal_type=rng.choice(SIGNALS),
                    impact="opportunity"
                    if r < opportunity
                    else ("risk" if r < opportunity + risk else "watch"),
                    scope="dx" if rng.random() < 0.7 else "dx_dependency",
                    relevance=rng.randint(30, 95),
                    taxonomy_revision=TAXONOMY_REVISION,
                )
            )
            if plan.ref:
                session.add(ItemRef(item_id=item.id, kind="arxiv", value=plan.ref.split(":", 1)[1]))
            if plan.track in (T.OSS, T.COMMUNITY):
                metric = "stars" if plan.track == T.OSS else "points"
                rate = plan.theme.stars * rng.uniform(5, 60) * (3 if plan.ref else 1)
                value = rng.randint(5, 80)
                at = item.first_seen_at
                # collectors re-poll an item only while it is trending: about a month
                while at < min(NOW, item.first_seen_at + timedelta(days=30)):
                    snapshots.append(
                        {
                            "item_id": item.id,
                            "captured_at": at,
                            "metrics": {metric: int(value), "comments": int(value / 12)},
                        }
                    )
                    age = (at - item.first_seen_at).days
                    value += rate * math.exp(-age / 6) * rng.uniform(0.5, 1.5)
                    at += timedelta(days=1, hours=rng.uniform(-3, 3))
        if snapshots:
            session.execute(insert(ItemMetricSnapshot), snapshots)
        session.flush()
        groups: dict[tuple[int, str, str], list[Item]] = {}
        for n, plan in enumerate(plans):
            if plan.ref is None:
                groups.setdefault((plan.day, plan.theme.key, plan.keywords[0]), []).append(
                    items[f"demo-{n}"]
                )
        for group in groups.values():
            if len(group) < 2 or rng.random() < 0.4:
                continue
            group = sorted(group, key=lambda i: i.first_seen_at)[: rng.randint(2, 6)]
            story = Story(
                representative_item_id=group[0].id,
                title_ko=group[0].title,
                first_seen_at=group[0].first_seen_at,
                last_seen_at=group[-1].first_seen_at,
                item_count=len(group),
                source_count=len({i.source_id for i in group}),
                tracks=sorted({i.track.value for i in group}),
                max_relevance=80,
            )
            session.add(story)
            session.flush()
            for j, item in enumerate(group):
                session.add(
                    StoryItem(
                        item_id=item.id,
                        story_id=story.id,
                        relation=Relation.SEED if j == 0 else Relation.NEAR,
                        similarity=None if j == 0 else 0.8,
                        joined_at=item.first_seen_at,
                    )
                )
    print(f"seeded {len(plans)} reports, {len(snapshots)} metric snapshots into {database}")


if __name__ == "__main__":
    main()
