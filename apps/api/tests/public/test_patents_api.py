"""GET /api/public/patents (plan 19 §1, §4): the 특허 menu by field, company and office, with
the data-coverage block; counts from patent_daily_stats, theme bars and documents live."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.content.models import Item
from news_insight.patents.models import PatentDailyStat, PatentMeta, PatentSource
from news_insight.sources.enums import Track
from news_insight.stories.models import Relation, Story, StoryItem
from tests.documents import card, document, source

pytestmark = pytest.mark.db

URL = "/api/public/patents"
AS_OF = date(2026, 10, 3)  # NOW is 2026-10-04 12:00 KST


def at(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC) - timedelta(hours=9)


def stat(
    session: Session,
    day: date,
    n: int,
    *,
    dim: str = "total",
    field: str = "display_av",
    src: str = "news",
    **keys: str,
) -> None:
    session.add(PatentDailyStat(day=day, dim=dim, field=field, source=src, n=n, **keys))
    session.flush()


def patent(
    session: Session,
    slug: str,
    day: date,
    *,
    field: str = "display_av",
    themes: list[str] | None = None,
    company_keys: list[str] | None = None,
    kind: PatentSource = PatentSource.NEWS,
) -> Item:
    if kind is PatentSource.NEWS:
        src = source(session, "ipwatch", category="ip_office", track=Track.RESEARCH_IP)
    else:
        src = source(session, "epo-eps", category="patent_office", track=Track.RESEARCH_IP)
    item = document(session, src, slug, published=at(day), seen=at(day))
    if themes is not None:
        card(session, item, field=field, themes=themes, signal_type="ip")
    session.add(
        PatentMeta(
            item_id=item.id,
            publication_number=f"EP{item.id}",
            kind="A1",
            office="EP",
            cpc=[],
            ipc=["H10K 59/00"],
            applicants=["Samsung Display Co., Ltd."] if company_keys else [],
            company_keys=company_keys or [],
            field=field,
            fields=[field],
            source=kind,
        )
    )
    session.flush()
    return item


def get(client: TestClient, headers: dict[str, str], **params: Any) -> Any:
    response = client.get(URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_overview_kpis_and_coverage(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    stat(db_session, AS_OF, 3)
    stat(db_session, AS_OF, 2, src="eps", field="semis")
    stat(db_session, date(2026, 8, 20), 1)
    patent(db_session, "own", date(2026, 9, 30), company_keys=["samsungdisplay"])
    patent(db_session, "plain", date(2026, 9, 29))

    body = get(public_client, public_headers)

    assert body["kind"] == "patent" and body["as_of"] == "2026-10-03"
    coverage = body["coverage"]
    assert (coverage["news"], coverage["eps"], coverage["ops"]) == (3, 2, 0)
    assert "OPS" in coverage["note"]
    kpis = body["overview"]["kpis"]
    assert (kpis["count"], kpis["previous"]) == (5, 1)
    assert kpis["company_share"] == 0.5 and kpis["company_docs"] == 1
    assert kpis["watched_count"] == 1
    rows = {row["key"]: row["counts"] for row in body["overview"]["heatmap"]["rows"]}
    assert rows["display_av"][-1] == 3 and rows["semis"][-1] == 2
    assert body["overview"]["insight"] is None

    # coverage rides along on every tab
    assert get(public_client, public_headers, tab="trends")["coverage"]["news"] == 3


def test_fields_tab_theme_bars_are_counted_live(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    stat(db_session, AS_OF, 3)
    stat(db_session, AS_OF, 2, dim="company", company_key="samsungdisplay")
    stat(db_session, AS_OF, 1, dim="company", src="eps", company_key="samsungdisplay")
    panel = ["display_av__display_panel"]
    a = patent(db_session, "a", date(2026, 9, 30), themes=panel, company_keys=["samsungdisplay"])
    b = patent(db_session, "b", date(2026, 9, 28), themes=[*panel, "display_av__xr_spatial"])
    patent(db_session, "c", date(2026, 8, 25), themes=panel)  # previous window
    patent(db_session, "d", date(2026, 9, 27), field="semis", themes=["semis__memory_storage"])

    body = get(public_client, public_headers, tab="fields", field="display_av")

    detail = body["fields"]["detail"]
    themes = {t["key"]: (t["count"], t["previous"]) for t in detail["themes"]}
    assert themes["display_av__display_panel"] == (2, 1)
    assert themes["display_av__xr_spatial"] == (1, 0)
    assert detail["themes"][0]["key"] == "display_av__display_panel"
    assert "semis__memory_storage" not in themes
    assert detail["companies"][0]["key"] == "samsungdisplay"
    assert detail["companies"][0]["count"] == 3  # summed over sources
    assert detail["orgs"] == []
    assert [d["id"] for d in detail["documents"]] == [a.id, b.id]  # watched first, then newest


def test_companies_tab_and_office_trends(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    stat(db_session, AS_OF, 4, dim="company", company_key="samsungdisplay")
    stat(db_session, AS_OF, 2, dim="company", field="semis", src="eps", company_key="apple")
    stat(db_session, AS_OF, 5, dim="company", company_key="google")
    for back in range(1, 9):
        stat(db_session, AS_OF - timedelta(weeks=back), 1, dim="office", src="eps", office="EP")
    stat(db_session, AS_OF, 12, dim="office", src="eps", office="EP")
    stat(db_session, AS_OF, 2, dim="office", office="US")

    body = get(public_client, public_headers, tab="companies")
    ranking = body["companies"]["ranking"]
    assert [r["key"] for r in ranking] == ["google", "samsungdisplay", "apple"]
    assert [r["watched"] for r in ranking] == [False, True, True]
    watched = [w["company"]["key"] for w in body["companies"]["watch"]["companies"]]
    assert watched == ["samsungdisplay", "apple"]
    kind = public_client.get(
        URL, params={"tab": "companies", "kind": "org"}, headers=public_headers
    )
    assert kind.status_code == 200 and kind.json()["companies"]["kind"] == "company"

    trends = get(public_client, public_headers, tab="trends", period="week")["trends"]
    assert trends["regions_axis"] == "office"
    offices = {s["key"]: s for s in trends["regions"]}
    assert offices["EP"]["label"] == "유럽(EPO)" and offices["EP"]["flag"] == "rise"
    assert offices["US"]["counts"][-1] == 2


def test_documents_tab_press_then_watched(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    reported = patent(db_session, "reported", date(2026, 9, 20), themes=[])
    watched = patent(db_session, "watched", date(2026, 9, 21), company_keys=["samsungdisplay"])
    plain = patent(db_session, "plain", date(2026, 9, 25), field="semis", kind=PatentSource.EPS)
    story = Story(
        representative_item_id=reported.id,
        title_ko="보도",
        first_seen_at=reported.first_seen_at,
        last_seen_at=reported.first_seen_at,
        item_count=3,
        source_count=3,
        tracks=["research_ip"],
        max_relevance=50,
    )
    db_session.add(story)
    db_session.flush()
    db_session.add(
        StoryItem(
            item_id=reported.id,
            story_id=story.id,
            relation=Relation.SEED,
            similarity=None,
            joined_at=reported.first_seen_at,
        )
    )
    db_session.flush()

    page = get(public_client, public_headers, tab="documents")["documents"]

    assert [d["id"] for d in page["items"]] == [reported.id, watched.id, plain.id]
    first, second, third = page["items"]
    assert first["press"] == 3 and second["watched"] is True and third["press"] == 0
    assert second["publication_number"] == f"EP{watched.id}" and second["office"] == "EP"
    assert second["applicants"] == ["Samsung Display Co., Ltd."]
    assert third["patent_source"] == "eps" and third["field"] == "semis"

    def ids(**params: Any) -> list[int]:
        found = get(public_client, public_headers, tab="documents", **params)["documents"]
        return [d["id"] for d in found["items"]]

    assert ids(field="semis") == [plain.id]
    assert ids(company="samsungdisplay") == [watched.id]
    assert ids(period="week") == []


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"tab": "today"}, 422),
        ({"period": "year"}, 422),
        ({"field": "nope"}, 422),
        ({"page": 101}, 422),
        ({"tab": "companies", "company": "nope"}, 404),
    ],
)
def test_bad_params(
    public_client: TestClient,
    public_headers: dict[str, str],
    params: dict[str, Any],
    code: int,
) -> None:
    assert public_client.get(URL, params=params, headers=public_headers).status_code == code
