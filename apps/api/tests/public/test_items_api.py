from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.public.seed import seed_corpus

pytestmark = pytest.mark.db


@pytest.fixture
def ids(db_session: Session) -> dict[str, int]:
    return seed_corpus(db_session)


def feed(client: TestClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    response = client.get("/api/public/items", params=params, headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def titles(body: dict[str, Any]) -> list[str]:
    return [row["title"] for row in body["items"]]


def test_default_feed_is_dx_relevant_last_7_days_one_row_per_story(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    body = feed(public_client, public_headers)
    assert titles(body) == [
        "Galaxy agent OS",
        "OLED burn-in compensation",
        "oled-compensation repo",
    ]
    assert body["total"] == 3
    assert body["items_total"] == 4
    lead = body["items"][0]
    assert lead["title_ko"] == "[KO] Galaxy agent OS"
    assert lead["field"] == "ai"
    assert lead["signal_type"] == "launch" and "businesses" not in lead
    assert lead["story"] == {
        "id": lead["story"]["id"],
        "item_count": 2,
        "source_count": 2,
        "tracks": ["news"],
    }
    assert lead["source_name"] == "The Verge"
    assert "source_key" not in lead


def test_scope_all_shows_excluded_and_irrelevant(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    body = feed(public_client, public_headers, scope="all")
    assert set(titles(body)) >= {"HBM capacity expansion", "커뮤니티 잡담"}
    assert "Failed card" not in titles(body)
    assert "Stale revision" not in titles(body)


def test_filters_are_or_within_an_axis_and_and_across_axes(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    def pick(**params: Any) -> set[str]:
        return set(titles(feed(public_client, public_headers, **params)))

    assert pick(field="display_av") == {"OLED burn-in compensation", "oled-compensation repo"}
    assert pick(signal="launch") == {"Galaxy agent OS"}
    assert pick(signal=["research", "launch"]) == {"Galaxy agent OS", "OLED burn-in compensation"}
    assert pick(field="display_av", signal="ecosystem") == {"oled-compensation repo"}
    assert pick(theme="display_av__display_panel") == {
        "OLED burn-in compensation",
        "oled-compensation repo",
    }
    assert pick(impact="opportunity") == {"Galaxy agent OS", "OLED burn-in compensation"}
    assert pick(track="oss") == {"oled-compensation repo"}


def test_a_story_stays_visible_when_only_a_follow_up_matches(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    body = feed(public_client, public_headers, region="kr")
    assert titles(body) == ["에이전트 OS 국내 보도"]
    assert body["items"][0]["story"]["item_count"] == 2


def test_period_and_scope_dx_only(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    assert "6G radio study items" in titles(feed(public_client, public_headers, period="30d"))
    assert "6G radio study items" not in titles(
        feed(public_client, public_headers, period="30d", scope="dx")
    )
    assert feed(public_client, public_headers, period="1d")["total"] == 1


def test_search_matches_korean_title_original_title_and_keywords(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    assert set(titles(feed(public_client, public_headers, q="oled"))) == {
        "OLED burn-in compensation",
        "oled-compensation repo",
    }
    assert titles(feed(public_client, public_headers, q="번인")) == ["oled-compensation repo"]
    assert titles(feed(public_client, public_headers, q="100%")) == []


def test_sort_by_relevance_and_coverage(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    assert titles(feed(public_client, public_headers, sort="relevance")) == [
        "Galaxy agent OS",
        "OLED burn-in compensation",
        "oled-compensation repo",
    ]
    assert titles(feed(public_client, public_headers, sort="coverage"))[0] == "Galaxy agent OS"


def test_paging(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    body = feed(public_client, public_headers, size=2, page=2)
    assert titles(body) == ["oled-compensation repo"]
    assert (body["page"], body["size"], body["total"]) == (2, 2, 3)


@pytest.mark.parametrize(
    "params",
    [
        {"field": "nope"},
        {"theme": "ai__nope"},
        {"signal": "nope"},
        {"impact": "nope"},
        {"track": "nope"},
        {"region": "nope"},
        {"scope": "nope"},
        {"period": "2w"},
        {"sort": "nope"},
        {"size": 51},
    ],
)
def test_invalid_parameters_are_rejected(
    public_client: TestClient, public_headers: dict[str, str], params: dict[str, Any]
) -> None:
    response = public_client.get("/api/public/items", params=params, headers=public_headers)
    assert response.status_code == 422


def test_item_detail_with_story_reports_and_cross_signals(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    lead = public_client.get(f"/api/public/items/{ids['Galaxy agent OS']}", headers=public_headers)
    assert lead.status_code == 200
    body = lead.json()
    assert body["item"]["summary_ko"] == ["Galaxy agent OS 요약"]
    assert [row["title"] for row in body["story_items"]] == ["에이전트 OS 국내 보도"]
    assert body["signals"] == []
    paper = public_client.get(
        f"/api/public/items/{ids['OLED burn-in compensation']}", headers=public_headers
    ).json()
    assert [(row["title"], row["track"], row["ref"]) for row in paper["signals"]] == [
        ("oled-compensation repo", "oss", "arxiv:2610.00001")
    ]
    assert "oled-compensation repo" in [row["title"] for row in paper["same_field"]]


def test_item_detail_hides_cards_that_are_not_published(
    public_client: TestClient, public_headers: dict[str, str], ids: dict[str, int]
) -> None:
    for title in ("Failed card", "Stale revision"):
        response = public_client.get(f"/api/public/items/{ids[title]}", headers=public_headers)
        assert response.status_code == 404
    assert public_client.get("/api/public/items/999999", headers=public_headers).status_code == 404


def test_archive_pages_stay_out_of_the_reader(
    public_client: TestClient,
    public_headers: dict[str, str],
    ids: dict[str, int],
    db_session: Session,
) -> None:
    from datetime import timedelta

    from news_insight.content.models import Item

    item = db_session.get(Item, ids["Galaxy agent OS"])
    assert item is not None
    item.published_at = item.first_seen_at - timedelta(days=400)  # found today, written last year
    db_session.flush()

    assert "Galaxy agent OS" not in titles(feed(public_client, public_headers))
