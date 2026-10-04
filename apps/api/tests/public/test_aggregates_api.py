from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.public.seed import seed_corpus

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def corpus(db_session: Session) -> dict[str, int]:
    return seed_corpus(db_session)


def get(client: TestClient, headers: dict[str, str], path: str, **params: Any) -> Any:
    response = client.get(f"/api/public/{path}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_facets_count_reports_in_the_window(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "facets")
    assert body["field"] == {"ai": 2, "display_av": 2}
    assert body["theme"] == {"ai__ai_agents": 2, "display_av__display_panel": 2}
    assert body["signal"] == {"launch": 2, "research": 1, "ecosystem": 1}
    assert body["impact"] == {"opportunity": 3, "watch": 1}
    assert body["track"] == {"news": 2, "research_ip": 1, "oss": 1}
    assert body["region"] == {"global_en": 3, "kr": 1}
    assert body["scope"] == {"dx": 4, "excluded": 1, "irrelevant": 1}


def test_facet_ignores_its_own_axis_but_applies_the_others(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "facets", field="ai")
    assert body["field"] == {"ai": 2, "display_av": 2}
    assert body["signal"] == {"launch": 2}
    assert body["track"] == {"news": 2}


def test_insights_compare_keywords_with_the_previous_window(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "insights")
    assert body["total"] == 4
    assert body["previous_total"] == 1
    keywords = {row["key"]: row for row in body["keywords"]}
    assert keywords["ai에이전트"] == {
        "key": "ai에이전트",
        "label": "AI 에이전트",
        "count": 2,
        "previous": 1,
        "change": 100.0,
        "is_new": False,
    }
    assert keywords["oled"]["count"] == 2
    assert keywords["oled"]["is_new"] is True
    assert keywords["oled"]["change"] is None
    assert set(body["related_keywords"]) == {"갤럭시", "번인"}
    assert body["fields"] == [{"key": "ai", "count": 2}, {"key": "display_av", "count": 2}]
    assert body["signal_types"] == [
        {"key": "launch", "count": 2},
        {"key": "ecosystem", "count": 1},
        {"key": "research", "count": 1},
    ]
    assert body["impacts"] == [{"key": "opportunity", "count": 3}, {"key": "watch", "count": 1}]


def test_insights_for_all_time_have_no_previous_window(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "insights", period="all")
    assert body["previous_total"] is None
    assert all(row["previous"] is None for row in body["keywords"])
