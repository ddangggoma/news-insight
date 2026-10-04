from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.public.radar import lifecycle, z_score
from tests.public.seed import seed_corpus

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def corpus(db_session: Session) -> dict[str, int]:
    return seed_corpus(db_session)


def get(client: TestClient, headers: dict[str, str], path: str, **params: Any) -> Any:
    response = client.get(f"/api/public/{path}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def by_key(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in rows}


def test_radar_defaults_to_the_current_iso_week(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "radar", period="week")
    window = body["window"]
    assert (window["kind"], window["key"]) == ("week", "2026-W40")
    assert (window["prev_key"], window["next_key"]) == ("2026-W39", "2026-W41")
    assert window["is_current"] is True
    # Sunday 12:00 KST: 6.5 of 7 days are past
    assert window["elapsed"] == pytest.approx(6.5 / 7, abs=0.001)
    assert body["periods"][0] == "2026-W33"
    assert body["periods"][-1] == "2026-W40"
    closed = get(public_client, public_headers, "radar", period="week", key="2026-W39")
    assert closed["window"]["elapsed"] is None


def test_radar_kpis_per_window(public_client: TestClient, public_headers: dict[str, str]) -> None:
    kpis = get(public_client, public_headers, "radar", period="week", key="2026-W40")["kpis"]
    assert kpis["items"] == [0, 0, 0, 0, 0, 0, 1, 4]
    # the two agent reports are one story
    assert kpis["stories"][-2:] == [1, 3]
    assert kpis["sources"][-1] == 4
    assert kpis["research"][-1] == 2
    assert (kpis["new_stories"], kpis["cross_track_stories"]) == (1, 0)


def test_radar_scores_fields_and_themes(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "radar", period="week", key="2026-W40")
    fields = by_key(body["fields"])
    assert [row["key"] for row in body["fields"]][:2] == ["ai", "display_av"]
    ai = fields["ai"]
    assert ai["counts"] == [0, 0, 0, 0, 0, 0, 0, 2]
    assert (ai["change"], ai["z"], ai["state"], ai["sources"]) == (None, 2.0, "new", 2)
    assert ai["tracks"] == {"news": 2, "community": 0, "research_ip": 0, "oss": 0}
    assert ai["impacts"] == {"opportunity": 2, "risk": 0, "watch": 0}
    display = fields["display_av"]
    assert display["tracks"] == {"news": 0, "community": 0, "research_ip": 1, "oss": 1}
    network = fields["connectivity"]
    assert network["counts"][-2:] == [1, 0]
    assert network["change"] == -100.0
    assert network["state"] is None
    assert network["previous_tracks"]["news"] == 1

    themes = by_key(body["themes"])
    oled = themes["display_av__display_panel"]
    assert (oled["field"], oled["counts"][-1], oled["state"]) == ("display_av", 2, "new")
    assert set(themes) == {
        "ai__ai_agents",
        "display_av__display_panel",
        "connectivity__cellular_5g_6g",
    }


def test_radar_keywords_normalize_and_track_lifecycle(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "radar", period="week", key="2026-W40")
    keywords = by_key(body["keywords"])
    # "AI 에이전트" and "AI에이전트" are one keyword; single-mention keywords are left out
    assert set(keywords) == {"ai에이전트", "oled"}
    agent = keywords["ai에이전트"]
    assert agent["label"] == "AI 에이전트"
    assert agent["counts"] == [0, 0, 0, 0, 0, 0, 1, 2]
    assert agent["state"] == "rising"
    assert agent["field"] == "ai"
    assert keywords["oled"]["state"] == "new"
    assert body["pairs"] == []


def test_radar_keyword_pairs_with_lift(
    public_client: TestClient,
    public_headers: dict[str, str],
    db_session: Session,
    corpus: dict[str, int],
) -> None:
    db_session.execute(
        update(ItemCard)
        .where(ItemCard.item_id == corpus["OLED burn-in compensation"])
        .values(keywords=["OLED", "번인"])
    )
    body = get(public_client, public_headers, "radar", period="week", key="2026-W40")
    # 4 items this week, oled and 번인 in 2 each and together in both: lift 2 * 4 / (2 * 2)
    assert body["pairs"] == [{"a": "oled", "b": "번인", "count": 2, "lift": 2.0, "is_new": True}]


def test_radar_signal_type_is_a_filter(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(
        public_client, public_headers, "radar", period="week", key="2026-W40", signal="research"
    )
    assert [row["key"] for row in body["fields"]] == ["display_av"]
    assert body["kpis"]["items"][-1] == 1
    assert body["taxonomy_revised_on"] == "2026-10-05"
    everything = get(public_client, public_headers, "radar", period="week", scope="all")
    assert {row["key"] for row in everything["fields"]} >= {"semis", "platform_sw"}


def test_radar_topic_theme(public_client: TestClient, public_headers: dict[str, str]) -> None:
    body = get(
        public_client,
        public_headers,
        "radar/topic",
        period="week",
        key="2026-W40",
        kind="theme",
        value="display_av__display_panel",
    )
    topic = body["topic"]
    assert topic["counts"] == [0, 0, 0, 0, 0, 0, 0, 2]
    assert topic["tracks"]["research_ip"] == 1
    assert body["themes"] == []
    assert body["keywords"][0] == {"key": "oled", "label": "OLED", "count": 2}
    assert body["signal_types"] == [
        {"key": "ecosystem", "count": 1},
        {"key": "research", "count": 1},
    ]
    assert sum(row["count"] for row in body["regions"]) == 2
    assert {row["title"] for row in body["stories"]} == {
        "OLED burn-in compensation",
        "oled-compensation repo",
    }


def test_radar_topic_keyword(public_client: TestClient, public_headers: dict[str, str]) -> None:
    body = get(
        public_client,
        public_headers,
        "radar/topic",
        period="week",
        key="2026-W40",
        kind="keyword",
        value="ai에이전트",
    )
    assert body["topic"]["counts"][-2:] == [1, 2]
    assert body["topic"]["label"] == "AI 에이전트"
    assert body["themes"] == [{"key": "ai__ai_agents", "count": 2}]
    assert [row["key"] for row in body["keywords"]] == ["갤럭시"]
    # both reports are one story, so one row
    assert len(body["stories"]) == 1


def test_radar_topic_field_honours_scope_and_quiet_topics(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    common = {"period": "week", "key": "2026-W40", "kind": "field", "value": "semis"}
    body = get(public_client, public_headers, "radar/topic", scope="all", **common)
    assert body["topic"]["counts"][-1] == 1
    assert [row["title"] for row in body["stories"]] == ["HBM capacity expansion"]
    quiet = get(public_client, public_headers, "radar/topic", **common)
    assert quiet["topic"]["counts"] == [0] * 8
    assert quiet["topic"]["state"] is None
    assert quiet["stories"] == []


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("radar", {"period": "year"}),
        ("radar", {"period": "week", "key": "2026-W99"}),
        ("radar", {"period": "week", "scope": "nope"}),
        ("radar", {"period": "week", "signal": "nope"}),
        ("radar/topic", {"period": "week", "kind": "nope", "value": "x"}),
        ("radar/topic", {"period": "week", "kind": "field", "value": "nope"}),
        ("radar/topic", {"period": "week", "kind": "theme", "value": "ai"}),
        ("radar/topic", {"period": "week", "kind": "keyword"}),
    ],
)
def test_radar_rejects_invalid_parameters(
    public_client: TestClient, public_headers: dict[str, str], path: str, params: dict[str, Any]
) -> None:
    response = public_client.get(f"/api/public/{path}", params=params, headers=public_headers)
    assert response.status_code == 422


def test_scores() -> None:
    assert z_score([0, 0, 0, 2]) == 2.0
    # mean 5, observed deviation 1: the Poisson floor (√5) keeps this from reading as 7σ
    assert z_score([4, 6, 4, 6, 12]) == 3.13
    # noise from successive differences (±20 → deviation 14.1), above the Poisson floor
    assert z_score([40, 60, 40, 60, 62]) == 0.85
    # a steady decline is not noise: 25 → 14 reads as a fall, the plain deviation would hide it
    assert z_score([45, 39, 20, 28, 9, 16, 19, 14]) == -1.3
    assert lifecycle([0, 0, 0, 3], sources=3) == "new"
    assert lifecycle([0, 0, 0, 3], sources=1) == "steady"  # one outlet is not a new topic
    assert lifecycle([2, 2, 2, 8], sources=4) == "surging"
    assert lifecycle([2, 2, 2, 8], sources=1) == "rising"
    assert lifecycle([4, 4, 4, 4], sources=4) == "steady"
    assert lifecycle([6, 6, 6, 3], sources=3) == "falling"
    assert lifecycle([6, 6, 6, 0], sources=0) == "falling"
    assert lifecycle([0, 1, 0, 1], sources=1) is None


def test_failed_and_stale_cards_stay_out(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    assert db_session.scalar(select(ItemCard.id).limit(1)) is not None
    body = get(public_client, public_headers, "radar", period="week", scope="all")
    assert body["kpis"]["items"][-1] == 6


def test_radar_regions_concentration_and_flows(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "radar", period="week", key="2026-W40")
    ai = by_key(body["fields"])["ai"]
    assert ai["regions"] == {"kr": 1, "global_en": 1, "jp": 0, "greater_china": 0, "eu_other": 0}
    assert set(ai["first_seen"]) == {"kr", "global_en"}
    # one report each from two outlets
    assert ai["effective_sources"] == 2.0
    assert ai["official"] == 0
    # the repo (oss, 50 h ago) and the paper (research, 26 h ago) share an arXiv id
    assert body["flows"] == {
        "chains": 1,
        "origins": {"oss": 1},
        "links": [{"source": "oss", "target": "research_ip", "count": 1, "median_hours": 24.0}],
        "ref_kinds": {"arxiv": 1},
    }
    earlier = get(public_client, public_headers, "radar", period="week", key="2026-W39")
    assert earlier["flows"]["chains"] == 0


def test_radar_topic_carries_concentration(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(
        public_client,
        public_headers,
        "radar/topic",
        period="week",
        key="2026-W40",
        kind="keyword",
        value="oled",
    )
    assert body["topic"]["effective_sources"] == 2.0
    assert body["topic"]["regions"]["global_en"] == 2


def test_normalized_share_weighs_every_track_equally() -> None:
    from news_insight.public.radar import normalized_share

    # 4 of 10 news reports and 1 of 2 research reports: (40% + 50%) / 2
    assert normalized_share({"news": 4, "research_ip": 1}, {"news": 10, "research_ip": 2}) == 45.0
    assert normalized_share({"news": 4}, {"news": 0}) is None


def test_radar_topics_carry_capped_counts_and_share(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "radar", period="week", key="2026-W40")
    theme = {row["key"]: row for row in body["themes"]}["display_av__display_panel"]
    assert theme["capped"] == 2
    assert 0 < theme["normalized_share"] <= 100
