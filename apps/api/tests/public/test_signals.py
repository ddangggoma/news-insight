from datetime import UTC, date, datetime
from typing import Any

import pytest

from news_insight.public.schemas import (
    Anomaly,
    Calendar,
    Engagement,
    FieldLink,
    Flows,
    KeywordCount,
    KeywordPair,
    Radar,
    RadarKpis,
    RadarWindow,
    ThemeEngagement,
    Topic,
)
from news_insight.public.signals import radar_signals, share_drop_z
from news_insight.public.stats import (
    count_z,
    noise_variance,
    rate_z,
    shrunk_share,
    two_proportion_z,
    zero_chance,
)


def mix(news: int = 0, community: int = 0, research_ip: int = 0, oss: int = 0) -> dict[str, int]:
    return {"news": news, "community": community, "research_ip": research_ip, "oss": oss}


def topic(key: str, counts: list[int], **patch: Any) -> Topic:
    values: dict[str, Any] = {
        "key": key,
        "label": None,
        "field": key.split("__")[0],
        "counts": counts,
        "change": None,
        "z": 0.0,
        "state": None,
        "sources": 3,
        "tracks": mix(counts[-1]),
        "previous_tracks": mix(counts[-2]),
        "baseline_tracks": mix(sum(counts[:-1])),
        "impacts": {"opportunity": 0, "risk": 0, "watch": 0},
        "regions": {"kr": 0, "global_en": counts[-1], "jp": 0, "greater_china": 0, "eu_other": 0},
        "first_seen": {},
        "official": 0,
        "effective_sources": 3.0,
    }
    return Topic(**{**values, **patch})


RADAR = Radar(
    window=RadarWindow(
        kind="week",
        key="2026-W40",
        start=datetime.fromisoformat("2026-09-28T00:00:00+09:00"),
        end=datetime.fromisoformat("2026-10-05T00:00:00+09:00"),
        prev_key="2026-W39",
        next_key="2026-W41",
        is_current=True,
        elapsed=0.5,
    ),
    periods=["2026-W37", "2026-W38", "2026-W39", "2026-W40"],
    kpis=RadarKpis(
        items=[10, 10, 12, 20],
        stories=[8, 8, 9, 15],
        sources=[5, 5, 6, 8],
        research=[3, 3, 4, 9],
        new_stories=4,
        cross_track_stories=1,
    ),
    # half of all reports come from Korean outlets
    fields=[
        topic(
            "ai",
            [4, 4, 5, 12],
            z=7.0,
            regions={"kr": 6, "global_en": 6, "jp": 0, "greater_china": 0, "eu_other": 0},
        )
    ],
    themes=[
        topic("ai__ai_agents", [2, 2, 2, 9], z=7.0, state="surging", sources=6),
        topic(
            "robotics_mobility__humanoid_embodied",
            [0, 1, 1, 6],
            z=3.0,
            state="rising",
            tracks=mix(1, 0, 3, 2),
        ),
        topic(
            "display_av__xr_spatial",
            [5, 6, 5, 6],
            z=0.5,
            state="steady",
            tracks=mix(5, 3, 0, 0),
            baseline_tracks=mix(6, 3, 8, 3),
        ),
        topic("connectivity__cellular_5g_6g", [6, 6, 6, 1], z=-5.0, state="falling"),
    ],
    keywords=[
        topic("유리기판", [0, 0, 0, 3], label="유리기판", field="semis", state="new"),
        topic("hbm4", [1, 1, 1, 4], label="HBM4", field="semis", state="rising"),
        topic("온디바이스ai", [2, 2, 2, 5], label="온디바이스 AI", field="ai", state="rising"),
    ],
    pairs=[
        KeywordPair(a="hbm4", b="온디바이스ai", count=3, lift=3.2, is_new=True),
        KeywordPair(a="hbm4", b="유리기판", count=2, lift=1.5, is_new=False),
    ],
    flows=Flows(chains=0, origins={}, links=[]),
    engagement=Engagement(measured=0, themes=[], top=[]),
    calendar=Calendar(start=date(2026, 7, 13), days=[], anomalies=[]),
    field_links=[],
)


def by_tone(radar: Radar) -> dict[str, Any]:
    return {signal.tone: signal for signal in radar_signals(radar)}


def test_surge_new_early_shift_link_and_cooling() -> None:
    signals = by_tone(RADAR)
    assert signals["surge"].title == "AI 에이전트"
    assert "직전 3주 같은 시점 평균 2.0건" in signals["surge"].detail
    assert (signals["new"].focus.kind, signals["new"].focus.key) == ("keyword", "유리기판")
    assert signals["early"].title == "휴머노이드·Embodied AI"
    assert signals["shift"].title == "XR·공간컴퓨팅·AI 글래스"
    assert "직전 3주 같은 시점 55% → 이번 0%" in signals["shift"].detail
    assert signals["link"].title == "HBM4 × 온디바이스 AI"
    assert "첫 동시 언급" in signals["link"].detail
    assert signals["cool"].title == "5G-Adv·6G"
    # XR's chatter is up too, but a theme takes one card
    assert "hype" not in signals


def test_a_closed_window_says_plain_baseline() -> None:
    closed = RADAR.model_copy(
        update={"window": RADAR.window.model_copy(update={"is_current": False, "elapsed": None})}
    )
    assert "직전 3주 평균 2.0건" in by_tone(closed)["surge"].detail


def test_chatter_that_outruns_research_once_per_theme() -> None:
    hot = topic(
        "platform_sw__device_os",
        [3, 3, 3, 9],
        z=0.8,
        tracks=mix(6, 2, 1, 0),
        baseline_tracks=mix(6, 3, 6, 0),
    )
    signals = radar_signals(RADAR.model_copy(update={"themes": [*RADAR.themes, hot]}))
    hype = next(s for s in signals if s.tone == "hype")
    assert hype.title == "디바이스 OS·플랫폼"
    assert hype.detail == (
        "뉴스·커뮤니티 8건으로 평소(3.0건)의 2.7배, 논문·오픈소스는 1건(평소 2.0건): "
        "화제가 실체보다 앞섬"
    )
    keys = [s.focus.key for s in signals if s.focus.kind == "theme"]
    assert len(set(keys)) == len(keys)


def test_thin_sourcing_and_korean_gaps() -> None:
    narrow = topic(
        "cloud_data__infra_ops", [2, 2, 2, 8], z=3.0, effective_sources=1.6, baseline_tracks=mix(18)
    )
    vendor = topic(
        "platform_sw__device_os", [2, 2, 2, 6], z=2.0, official=4, baseline_tracks=mix(15)
    )
    abroad = topic(
        "wasm",
        [0, 0, 1, 6],
        label="WASM",
        state="rising",
        regions={"kr": 0, "global_en": 6, "jp": 0, "greater_china": 0, "eu_other": 0},
    )
    rare = abroad.model_copy(update={"key": "rare", "label": "RARE", "counts": [0, 0, 0, 3]})
    signals = by_tone(
        RADAR.model_copy(
            update={"themes": [narrow, vendor], "keywords": [abroad, rare], "pairs": []}
        )
    )
    assert signals["thin"].title == "인프라 운영"
    assert "실효 출처 1.6곳" in signals["thin"].detail
    # 0.5^6 ≈ 1.6 %: six reports without a Korean one is unlikely; three (12.5 %) is not
    assert signals["gap"].title == "WASM"
    assert "해외 6건" in signals["gap"].detail
    assert "RARE" not in signals["gap"].detail
    only_vendor = by_tone(
        RADAR.model_copy(update={"themes": [vendor], "keywords": [], "pairs": []})
    )
    assert "뉴스 중 공식 발표 67%" in only_vendor["thin"].detail


def test_anomaly_days_returning_keywords_pull_and_category_links() -> None:
    radar = RADAR.model_copy(
        update={
            "keywords": [
                topic(
                    "메타버스",
                    [0, 0, 0, 4],
                    label="메타버스",
                    state="new",
                    returning=True,
                    first_ever=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                topic(
                    "one ui 9",
                    [0, 0, 2, 9],
                    label="One UI 9",
                    state="surging",
                    debut=True,
                    first_ever=datetime(2026, 9, 26, tzinfo=UTC),
                ),
            ],
            "pairs": [],
            "engagement": Engagement(
                measured=30,
                themes=[
                    ThemeEngagement(key="display_av__xr_spatial", score=80, items=20),
                    ThemeEngagement(key="ai__ai_agents", score=20, items=9),
                ],
                top=[],
            ),
            "calendar": Calendar(
                start=date(2026, 7, 13),
                days=[],
                anomalies=[
                    Anomaly(
                        day=date(2026, 8, 27),
                        field="ai",
                        count=40,
                        expected=13.5,
                        z=7.2,
                        keywords=[],
                    ),
                    Anomaly(
                        day=date(2026, 9, 30),
                        field="platform_sw",
                        count=25,
                        expected=3.5,
                        z=11.5,
                        keywords=[KeywordCount(key="갤럭시", label="갤럭시", count=9)],
                    ),
                ],
            ),
            "field_links": [FieldLink(a="frontier", b="security", count=3, previous=0)],
        }
    )
    signals = by_tone(radar)
    # only anomalies inside the window count, and the card opens the keyword behind them
    assert signals["event"].title == "9/30 플랫폼·소프트웨어"
    assert signals["event"].detail == "하루 25건, 평소 같은 요일 3.5건의 7.1배 · 갤럭시"
    assert (signals["event"].focus.kind, signals["event"].focus.key) == ("keyword", "갤럭시")
    assert signals["back"].title == "메타버스"
    assert signals["new"].title == "One UI 9"
    assert "처음 보도된 지 8일" in signals["new"].detail
    # XR: 6 of 22 mentions (27 %) but 80 % of the reactions and 20 of 30 reacting items
    assert signals["pull"].title == "XR·공간컴퓨팅·AI 글래스"
    assert "언급 비중 27%인데 반응(스타·포인트 증가) 비중 80%" in signals["pull"].detail
    assert signals["link"].title == "미래 기술 × 보안·신뢰"


def test_research_share_drop_is_tested_for_significance() -> None:
    big = topic(
        "a__b", [10, 10, 10, 30], tracks=mix(24, 0, 6, 0), baseline_tracks=mix(10, 0, 20, 0)
    )
    small = topic("a__b", [1, 1, 1, 3], tracks=mix(3, 0, 0, 0), baseline_tracks=mix(1, 0, 2, 0))
    assert share_drop_z(big) == pytest.approx(3.65, abs=0.05)  # 67 % → 20 % over 30 reports each
    assert share_drop_z(small) < 2


def test_no_cards_without_a_baseline() -> None:
    # right after collection starts every topic would read as a huge surge
    fresh = RADAR.model_copy(
        update={"kpis": RADAR.kpis.model_copy(update={"items": [0, 0, 3, 900]})}
    )
    assert radar_signals(fresh) == []
    assert radar_signals(RADAR) != []


def test_a_single_outlet_is_not_a_new_technology_or_a_korean_gap() -> None:
    dump = topic(
        "zigbee2mqtt",
        [0, 0, 0, 572],
        label="Zigbee2MQTT",
        state="new",
        sources=1,
        regions={"kr": 0, "global_en": 572, "jp": 0, "greater_china": 0, "eu_other": 0},
    )
    signals = by_tone(RADAR.model_copy(update={"keywords": [dump], "pairs": []}))
    assert "new" not in signals and "gap" not in signals


def test_an_empty_radar_stays_quiet() -> None:
    assert radar_signals(RADAR.model_copy(update={"themes": [], "keywords": [], "pairs": []})) == []


def test_candidates_list_every_match_before_ranking() -> None:
    found: dict[str, list[str]] = {}
    radar_signals(RADAR, candidates=found)
    assert found["surge"] == ["ai__ai_agents"]
    assert found["cool"] == ["connectivity__cellular_5g_6g"]
    assert found["link"] == ["hbm4×온디바이스ai"]


def test_shared_statistics() -> None:
    # Poisson floor: ten on a base of five is about 2σ, not 5σ
    assert count_z(10, [5, 5, 5, 5]) == pytest.approx(5 / 5**0.5)
    assert count_z(2, [0, 0, 0]) == 2.0  # the variance never drops below 1
    # successive differences: a steady fall is not counted as noise
    assert noise_variance([10, 8, 6, 4]) == 2.0
    assert noise_variance([5]) == 0.0
    assert rate_z(9, 4) == 2.5
    assert two_proportion_z(10, 20, 0, 8) > 2
    assert two_proportion_z(1, 0, 1, 2) == 0.0
    assert zero_chance(6, 0.5) == pytest.approx(0.015625)
    assert zero_chance(3, 0) == 1.0
    # three of three is pulled toward the overall 30 %; thirty of thirty barely moves
    assert shrunk_share(3, 3, 0.3) == pytest.approx(6 / 13)
    assert shrunk_share(30, 30, 0.3) > 0.8
