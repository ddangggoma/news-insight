"""GET /api/public/research (plan 19 §1, §4): one response per tab, windows ending on the last
day counted (at most yesterday, KST), counts from research_daily_stats, documents and watched
counts from research_signals (rebuilt here with recompute_signals, as the nightly job does)."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.insights.models import (
    DomainInsightRecord,
    InsightKind,
    InsightStatus,
    StatsDay,
)
from news_insight.insights.signals import recompute_signals
from news_insight.insights.stats import recompute_days
from news_insight.public import domain_cache
from news_insight.research.models import EnrichStatus, ResearchDailyStat, ResearchMeta
from news_insight.sources.enums import AccessMethod, Track
from news_insight.spotlight.candidates import HF_PAPERS
from news_insight.taxonomy.catalog import FIELDS
from tests.documents import card, document, mark_built, source
from tests.factories import build_source

pytestmark = pytest.mark.db

URL = "/api/public/research"
AS_OF = date(2026, 10, 3)  # NOW is 2026-10-04 12:00 KST: the stats end the day before
NOW_DAY = date(2026, 10, 4)


@pytest.fixture(autouse=True)
def _built(db_session: Session) -> None:
    """The nightly counts ran for every day up to AS_OF (enough history for every flag)."""
    mark_built(db_session, AS_OF - timedelta(days=900), AS_OF)


def signals(session: Session) -> None:
    recompute_signals(session, through=AS_OF, now=at(AS_OF + timedelta(days=1), 4))


def at(day: date, hour: int = 12) -> datetime:
    """`hour` o'clock KST on `day`."""
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC) - timedelta(hours=9)


def stat(
    session: Session,
    day: date,
    n: int,
    *,
    dim: str = "total",
    field: str = "ai",
    n_company: int = 0,
    **keys: str,
) -> None:
    session.add(ResearchDailyStat(day=day, dim=dim, field=field, n=n, n_company=n_company, **keys))
    session.flush()


def meta(
    session: Session,
    item: Item,
    *,
    company_keys: list[str] | None = None,
    institutions: list[dict[str, Any]] | None = None,
    cited_by: int | None = None,
    counts_by_year: list[dict[str, int]] | None = None,
    doi: str | None = None,
) -> None:
    session.add(
        ResearchMeta(
            item_id=item.id,
            doi=doi or f"10.1/{item.id}",
            venue="NeurIPS",
            institutions=institutions or [],
            countries=[],
            company_keys=company_keys or [],
            has_company=bool(company_keys),
            cited_by=cited_by,
            counts_by_year=counts_by_year or [],
            status=EnrichStatus.OK,
            enriched_at=at(AS_OF),
        )
    )
    session.flush()


def paper(
    session: Session,
    slug: str,
    day: date,
    *,
    field: str | None = "ai",
    refs: tuple[tuple[str, str], ...] = (),
    src: Any = None,
    url: str | None = None,
) -> Item:
    item = document(
        session,
        src or source(session, "arxiv"),
        slug,
        published=at(day),
        seen=at(day),
        refs=refs,
        url=url,
    )
    if field is not None:
        card(session, item, field=field, themes=[])
    return item


def get(client: TestClient, headers: dict[str, str], **params: Any) -> Any:
    response = client.get(URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.content) < 1_000_000
    return response.json()


def test_overview_kpis_heatmap_and_risers(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    stat(db_session, AS_OF, 30, n_company=12)  # current month: 2026-09-04 .. 10-03
    stat(db_session, date(2026, 9, 10), 10, field="semis")
    for day, n in ((date(2026, 8, 20), 5), (date(2026, 7, 20), 4), (date(2026, 6, 20), 6)):
        stat(db_session, day, n)
    stat(db_session, date(2026, 5, 20), 5)
    for day in (date(2026, 8, 21), date(2026, 7, 21), date(2026, 6, 21), date(2026, 5, 21)):
        stat(db_session, day, 10, field="semis")
    stat(db_session, date(2026, 10, 4), 100)  # today (partial): never counted
    own = paper(db_session, "own", date(2026, 9, 20))
    meta(db_session, own, company_keys=["samsungelectronics"])
    meta(db_session, paper(db_session, "peer", date(2026, 9, 21)), company_keys=["openai"])
    meta(db_session, paper(db_session, "rival", date(2026, 8, 10)), company_keys=["apple"])
    signals(db_session)

    body = get(public_client, public_headers)

    assert body["kind"] == "research" and body["tab"] == "overview" and body["period"] == "month"
    assert body["as_of"] == "2026-10-03" and body["stats_from"] == "2024-04-16"
    assert body["window"] == {"start": "2026-09-04", "end": "2026-10-03"}
    assert body["previous"] == {"start": "2026-08-05", "end": "2026-09-03"}
    assert body["fields"] is None and body["documents"] is None and body["coverage"] is None
    assert [f["key"] for f in body["field_options"]] == [f.key for f in FIELDS]
    overview = body["overview"]
    kpis = overview["kpis"]
    assert (kpis["count"], kpis["previous"]) == (40, 15)
    assert kpis["change"] == pytest.approx(25 / 15, abs=0.01)
    assert kpis["company_share"] == pytest.approx(0.3)
    assert (kpis["watched_count"], kpis["watched_previous"]) == (1, 1)
    assert kpis["rising_field"]["key"] == "ai"
    risers = overview["risers"]
    assert [r["key"] for r in risers] == ["ai"]  # semis is flat
    assert risers[0]["label"] == "AI 모델·에이전트"
    assert risers[0]["count"] == 30 and risers[0]["mean"] == 5 and risers[0]["ratio"] == 6
    assert risers[0]["z"] > 2
    heatmap = overview["heatmap"]
    assert len(heatmap["weeks"]) == 12
    assert heatmap["weeks"][-1] == {"start": "2026-09-27", "end": "2026-10-03"}
    rows = {row["key"]: row["counts"] for row in heatmap["rows"]}
    assert list(rows) == [f.key for f in FIELDS]
    assert rows["ai"][-1] == 30 and rows["semis"][8] == 10 and heatmap["max"] == 30
    assert overview["insight"] is None and overview["coverage_note"] is None


def test_period_windows_end_yesterday(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    week = get(public_client, public_headers, period="week")
    assert week["window"] == {"start": "2026-09-27", "end": "2026-10-03"}
    assert week["previous"] == {"start": "2026-09-20", "end": "2026-09-26"}
    quarter = get(public_client, public_headers, period="quarter")
    assert quarter["window"] == {"start": "2026-07-06", "end": "2026-10-03"}
    assert quarter["previous"] == {"start": "2026-04-07", "end": "2026-07-05"}


def test_fields_tab_themes_companies_orgs_and_documents(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    stat(db_session, AS_OF, 30)
    stat(db_session, date(2026, 8, 20), 5)
    stat(db_session, AS_OF, 10, field="semis")
    stat(db_session, AS_OF, 8, dim="theme", theme="ai__ai_agents")
    stat(db_session, date(2026, 8, 20), 2, dim="theme", theme="ai__ai_agents")
    stat(db_session, AS_OF, 3, dim="theme", theme="ai__foundation_models")
    stat(db_session, AS_OF, 4, dim="company", company_key="samsungelectronics")
    stat(db_session, date(2026, 8, 20), 1, dim="company", company_key="samsungelectronics")
    stat(db_session, AS_OF, 6, dim="company", company_key="openai")
    stat(
        db_session, AS_OF, 5, dim="org", org_name="Seoul National University", org_type="education"
    )
    stat(db_session, AS_OF, 2, dim="org", org_name="Tiny Startup", org_type="company")
    ai_paper = paper(db_session, "agents", date(2026, 9, 30))
    paper(db_session, "chips", date(2026, 9, 30), field="semis")
    signals(db_session)

    body = get(public_client, public_headers, tab="fields")

    tab = body["fields"]
    assert body["overview"] is None
    items = {f["key"]: f for f in tab["items"]}
    assert list(items) == [f.key for f in FIELDS]
    assert (items["ai"]["count"], items["ai"]["previous"]) == (30, 5)
    assert items["ai"]["change"] == 5.0
    assert tab["selected"] == "ai"  # the busiest field when none is asked for
    detail = tab["detail"]
    assert detail["key"] == "ai" and detail["count"] == 30
    themes = detail["themes"]
    assert len(themes) == 7  # every theme of the field, busiest first
    assert themes[0] == {
        "key": "ai__ai_agents",
        "label": "AI 에이전트",
        "count": 8,
        "previous": 2,
        "change": 3.0,
    }
    assert len(tab["buckets"]) == 12 and detail["series"][-1] == 30
    assert [c["key"] for c in detail["companies"]] == ["openai", "samsungelectronics"]
    samsung = detail["companies"][1]
    assert samsung["label"] == "삼성전자" and samsung["watched"] is True
    assert (samsung["count"], samsung["previous"]) == (4, 1)
    assert [(o["name"], o["org_type"]) for o in detail["orgs"]] == [
        ("Seoul National University", "education"),
        ("Tiny Startup", "company"),
    ]
    assert [d["id"] for d in detail["documents"]] == [ai_paper.id]
    assert detail["insight"] is None

    semis = get(public_client, public_headers, tab="fields", field="semis")["fields"]
    assert semis["selected"] == "semis" and semis["detail"]["count"] == 10
    for field in ("nope", "other"):  # unclassified papers are counted, not selectable
        bad = public_client.get(
            URL, params={"tab": "fields", "field": field}, headers=public_headers
        )
        assert bad.status_code == 422


def test_companies_tab_ranking_watch_and_detail(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    prev = date(2026, 8, 20)
    stat(db_session, AS_OF, 4, dim="company", company_key="samsungelectronics")
    stat(db_session, prev, 2, dim="company", company_key="samsungelectronics")
    stat(db_session, AS_OF, 2, dim="company", field="semis", company_key="samsungelectronics")
    stat(db_session, AS_OF, 9, dim="company", company_key="openai")
    stat(db_session, AS_OF, 1, dim="company", field="semis", company_key="apple")
    stat(db_session, AS_OF, 3, dim="org", org_name="Tiny Startup", org_type="company")
    stat(db_session, AS_OF, 7, dim="org", org_name="KAIST", org_type="education")
    stat(db_session, AS_OF, 2, dim="org", field="semis", org_name="MIT", org_type="education")
    # a name with rows of both types counts only its type's rows in each ranking
    stat(
        db_session, AS_OF, 5, dim="org", field="semis", org_name="Tiny Startup", org_type="facility"
    )
    own = paper(db_session, "own", date(2026, 9, 25))
    meta(
        db_session,
        own,
        company_keys=["samsungelectronics"],
        institutions=[
            {"name": "Samsung", "type": "company", "company_key": "samsungelectronics"},
            {"name": "KAIST", "type": "education", "company_key": None},
        ],
        counts_by_year=[{"year": 2026, "cited_by_count": 4}],
    )
    newer = paper(db_session, "newer", date(2026, 9, 28))
    meta(db_session, newer, company_keys=["samsungelectronics"])
    signals(db_session)

    body = get(public_client, public_headers, tab="companies")

    tab = body["companies"]
    assert tab["kind"] == "company"
    ranking = tab["ranking"]
    assert [(r["key"], r["entity"]) for r in ranking] == [
        ("openai", "company"),
        ("samsungelectronics", "company"),
        ("Tiny Startup", "org"),
        ("apple", "company"),
    ]
    samsung = ranking[1]
    assert (samsung["count"], samsung["previous"], samsung["change"]) == (6, 2, 2.0)
    assert samsung["watched"] is True and samsung["relation"] == "self"
    assert [(f["key"], f["count"]) for f in samsung["top_fields"]] == [("ai", 4), ("semis", 2)]
    assert ranking[0]["watched"] is False and ranking[2]["org_type"] == "company"
    assert ranking[2]["count"] == 3  # not the facility rows of the same name
    watch = tab["watch"]
    assert watch["total"] >= 2
    watched = {w["company"]["key"]: w for w in watch["companies"]}
    assert list(watched) == ["samsungelectronics", "apple"]
    assert watched["samsungelectronics"]["series"][-1] == 6
    assert watched["samsungelectronics"]["series"][-2] == 2
    assert [(f["key"], f["count"]) for f in watched["samsungelectronics"]["fields"]] == [
        ("ai", 4),
        ("semis", 2),
    ]
    assert len(watch["buckets"]) == 12
    assert tab["detail"] is None and tab["insight"] is None

    orgs = get(public_client, public_headers, tab="companies", kind="org")["companies"]
    assert [(r["key"], r["org_type"]) for r in orgs["ranking"]] == [
        ("KAIST", "education"),
        ("Tiny Startup", "facility"),
        ("MIT", "education"),
    ]
    assert orgs["ranking"][1]["count"] == 5

    detail = get(public_client, public_headers, tab="companies", company="samsungelectronics")
    company = detail["companies"]["detail"]
    assert company["key"] == "samsungelectronics" and company["label"] == "삼성전자"
    assert company["count"] == 6 and company["series"][-1] == 6
    assert [f["key"] for f in company["fields"]] == ["ai", "semis"]
    assert [d["id"] for d in company["documents"]] == [newer.id, own.id]  # 최근 문헌
    assert [d["id"] for d in company["top_documents"]] == [own.id, newer.id]  # by score

    org = get(public_client, public_headers, tab="companies", kind="org", org="KAIST")
    assert org["companies"]["detail"]["entity"] == "org"
    assert org["companies"]["detail"]["count"] == 7
    assert [d["id"] for d in org["companies"]["detail"]["documents"]] == [own.id]

    unknown = public_client.get(
        URL, params={"tab": "companies", "company": "nope"}, headers=public_headers
    )
    assert unknown.status_code == 404
    nowhere = public_client.get(
        URL, params={"tab": "companies", "org": "Nowhere U"}, headers=public_headers
    )
    assert nowhere.status_code == 404


def test_trends_tab_series_rest_and_rise_fall_flags(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    keys = [f.key for f in FIELDS if f.key not in ("ai", "semis", "connectivity")]
    for back in range(1, 9):  # the eight weeks before the current one
        day = AS_OF - timedelta(weeks=back)
        stat(db_session, day, 10, field="ai")
        stat(db_session, day, 10, field="semis")
        stat(db_session, day, 10, field="connectivity")
    stat(db_session, AS_OF, 40, field="ai")
    stat(db_session, AS_OF, 1, field="semis")
    stat(db_session, AS_OF, 10, field="connectivity")
    for rank, key in enumerate(keys[:8]):  # eight more fields, the last three go to 기타
        stat(db_session, AS_OF, 20 - rank, field=key)
    stat(db_session, AS_OF, 4, field="other")  # unclassified papers go to 기타 too
    for rank, country in enumerate(["US", "CN", "KR", "DE", "GB", "JP", "FR", "CA", "IN", "IT"]):
        stat(db_session, AS_OF, 20 - rank, dim="country", country=country)

    body = get(public_client, public_headers, tab="trends", period="week")

    trends = body["trends"]
    assert len(trends["buckets"]) == 12 and trends["history"] == 8
    series = {s["key"]: s for s in trends["fields"]}
    assert len(trends["fields"]) == 9 and trends["fields"][-1]["key"] == "rest"
    assert trends["fields"][-1]["label"] == "기타"
    assert series["ai"]["flag"] == "rise" and series["ai"]["counts"][-1] == 40
    assert series["semis"]["flag"] == "fall"
    assert series["connectivity"]["flag"] is None
    assert series["rest"]["counts"][-1] == (20 - 5) + (20 - 6) + (20 - 7) + 4
    assert trends["regions_axis"] == "country"
    regions = [s["key"] for s in trends["regions"]]
    assert regions[:3] == ["US", "CN", "KR"] and regions[-1] == "rest" and len(regions) == 9
    assert trends["regions"][2]["label"] == "한국"
    flags = {(f["axis"], f["key"]): f["flag"] for f in trends["flags"]}
    assert flags[("field", "ai")] == "rise" and flags[("field", "semis")] == "fall"
    assert ("field", "connectivity") not in flags


def hf_source(session: Session) -> Any:
    hf = build_source(
        key="hf-papers",
        name="Hugging Face",
        operator=HF_PAPERS,
        track=Track.RESEARCH_IP,
        category="academic_paper",
        access_method=AccessMethod.RESEARCH_API,
    )
    session.add(hf)
    session.flush()
    return hf


def test_documents_tab_scores_filters_and_pages(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    news = source(db_session, "verge", category="independent_media", track=Track.NEWS)
    hf = hf_source(db_session)
    talked = paper(
        db_session,
        "talked",
        date(2026, 9, 20),
        refs=(("arxiv", "2609.11111"),),
        url="https://arxiv.org/abs/2609.11111v2",
    )
    meta(
        db_session,
        talked,
        cited_by=9,
        doi="10.48550/arxiv.2609.11111",
        counts_by_year=[{"year": 2025, "cited_by_count": 6}, {"year": 2026, "cited_by_count": 9}],
    )
    for slug, day in (("one", date(2026, 9, 22)), ("two", date(2026, 9, 23)), ("late", NOW_DAY)):
        document(
            db_session, news, slug, published=at(day), seen=at(day), refs=(("arxiv", "2609.11111"),)
        )
    voted = paper(db_session, "voted", date(2026, 9, 21), src=hf)
    db_session.add_all(
        [
            ItemMetricSnapshot(item_id=voted.id, captured_at=at(AS_OF), metrics={"upvotes": 40}),
            # counted up to as_of: today's snapshot is not
            ItemMetricSnapshot(item_id=voted.id, captured_at=at(NOW_DAY), metrics={"upvotes": 90}),
        ]
    )
    chips = paper(db_session, "chips", date(2026, 9, 19), field="semis")
    meta(
        db_session,
        chips,
        company_keys=["samsungelectronics"],
        institutions=[
            {"name": "Samsung", "type": "company", "company_key": "samsungelectronics"},
            {"name": "KAIST", "type": "education", "company_key": None},
        ],
    )
    older = paper(db_session, "older", date(2026, 8, 1))
    paper(db_session, "today", NOW_DAY)
    signals(db_session)

    body = get(public_client, public_headers, tab="documents")

    page = body["documents"]
    assert (page["page"], page["size"], page["total"]) == (1, 20, 3)
    assert [d["id"] for d in page["items"]] == [voted.id, talked.id, chips.id]
    first, second, third = page["items"]
    assert first["upvotes"] == 40 and first["score"] == 40
    assert second["mentions"] == 2 and second["cited_by"] == 9 and second["venue"] == "NeurIPS"
    assert second["cited_growth"] == 3  # 2026's citations against 2025's
    assert second["score"] == pytest.approx(20 + 5 * 1.386, abs=0.1)
    assert second["field"] == "ai" and second["field_label"] == "AI 모델·에이전트"
    assert third["companies"][0]["key"] == "samsungelectronics" and third["watched"] is True
    assert third["orgs"] == ["KAIST"]

    def found(**params: Any) -> tuple[list[int], int]:
        tab = get(public_client, public_headers, tab="documents", **params)["documents"]
        return [d["id"] for d in tab["items"]], int(tab["total"])

    assert found(field="semis") == ([chips.id], 1)
    assert found(company="samsungelectronics") == ([chips.id], 1)
    assert found(org="KAIST") == ([chips.id], 1)
    assert found(company="samsungelectronics", org="MIT") == ([], 0)  # both filters hold
    assert older.id in found(period="quarter")[0]
    assert found(page=2) == ([], 3)
    missing = public_client.get(
        URL, params={"tab": "documents", "company": "nope"}, headers=public_headers
    )
    assert missing.status_code == 404


def test_listings_of_one_paper_fold_into_one_document(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    hf = hf_source(db_session)
    preprint = paper(
        db_session,
        "preprint",
        date(2026, 9, 20),
        refs=(("arxiv", "2609.33333"),),
        url="https://arxiv.org/abs/2609.33333v1",
    )
    meta(db_session, preprint, doi="10.48550/arxiv.2609.33333", company_keys=["openai"])
    listing = paper(
        db_session,
        "listing",
        date(2026, 9, 22),
        refs=(("arxiv", "2609.33333"),),
        src=hf,
        url="https://huggingface.co/papers/2609.33333",
    )
    db_session.add(
        ItemMetricSnapshot(item_id=listing.id, captured_at=at(AS_OF), metrics={"upvotes": 25})
    )
    signals(db_session)

    page = get(public_client, public_headers, tab="documents")["documents"]

    assert page["total"] == 1 and [d["id"] for d in page["items"]] == [preprint.id]
    assert page["items"][0]["upvotes"] == 25  # the group's signals ride on the lead
    assert page["items"][0]["companies"][0]["key"] == "openai"


def test_stats_totals_equal_the_documents_list(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    db_session.query(StatsDay).delete()
    for slug, day, field in (
        ("a", date(2026, 9, 10), "ai"),
        ("b", date(2026, 9, 30), "ai"),
        ("c", date(2026, 9, 15), "semis"),
        ("d", date(2026, 8, 20), "ai"),  # previous window
    ):
        paper(db_session, slug, day, field=field)
    unclassified = paper(db_session, "e", date(2026, 9, 12), field=None)
    days = [AS_OF - timedelta(days=back) for back in range(120)]
    recompute_days(db_session, days, now=at(NOW_DAY, 4))
    signals(db_session)

    overview = get(public_client, public_headers)["overview"]["kpis"]
    documents = get(public_client, public_headers, tab="documents")["documents"]
    fields = get(public_client, public_headers, tab="fields")["fields"]

    assert overview["count"] == documents["total"] == 4
    assert overview["previous"] == 1
    assert fields["items"][0]["count"] == len(fields["detail"]["documents"]) == 2
    assert fields["other"]["count"] == 1
    assert unclassified.id in [d["id"] for d in documents["items"]]


def test_as_of_is_the_last_day_built(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    db_session.query(StatsDay).filter(StatsDay.day == AS_OF).delete()  # 03:40 has not run yet

    body = get(public_client, public_headers)

    assert body["as_of"] == "2026-10-02"
    assert body["window"] == {"start": "2026-09-03", "end": "2026-10-02"}


def test_flags_are_off_when_the_history_is_short(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    db_session.query(StatsDay).filter(StatsDay.day < AS_OF - timedelta(days=70)).delete()
    for back in range(1, 12):
        stat(db_session, AS_OF - timedelta(days=30 * back), 5)
    stat(db_session, AS_OF, 50)

    overview = get(public_client, public_headers)["overview"]
    trends = get(public_client, public_headers, tab="trends")["trends"]

    assert overview["risers"] == [] and overview["kpis"]["rising_field"] is None
    assert overview["coverage_note"]
    ai = next(s for s in trends["fields"] if s["key"] == "ai")
    assert ai["counts"][-1] == 50 and ai["flag"] is None and ai["z"] is None
    assert trends["flags"] == [] and trends["coverage_note"]
    # nine weeks reach back 63 days: within the 70 days built
    weekly = get(public_client, public_headers, tab="trends", period="week")["trends"]
    assert next(s for s in weekly["fields"] if s["key"] == "ai")["flag"] == "rise"


def test_country_flags_wait_for_enrichment_coverage(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    db_session.query(StatsDay).delete()
    mark_built(
        db_session, AS_OF - timedelta(days=400), AS_OF - timedelta(days=7), research_enriched=10
    )
    mark_built(db_session, AS_OF - timedelta(days=6), AS_OF, research_enriched=90)
    for back in range(1, 9):
        day = AS_OF - timedelta(weeks=back)
        stat(db_session, day, 10)
        stat(db_session, day, 1, dim="country", country="KR")
    stat(db_session, AS_OF, 40)
    stat(db_session, AS_OF, 30, dim="country", country="KR")

    trends = get(public_client, public_headers, tab="trends", period="week")["trends"]

    assert next(s for s in trends["fields"] if s["key"] == "ai")["flag"] == "rise"
    korea = next(s for s in trends["regions"] if s["key"] == "KR")
    assert korea["counts"][-1] == 30 and korea["flag"] is None and korea["z"] is None
    assert {f["axis"] for f in trends["flags"]} == {"field"}
    assert "보강" in trends["coverage_note"]


def test_rising_field_needs_z_of_two(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    for back in range(1, 5):
        stat(db_session, AS_OF - timedelta(days=30 * back), 10)
    stat(db_session, AS_OF, 13)  # above the mean, z = 3 / √10 < 2

    overview = get(public_client, public_headers)["overview"]

    assert [r["key"] for r in overview["risers"]] == ["ai"]
    assert overview["kpis"]["rising_field"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"tab": "today"},
        {"period": "year"},
        {"page": 0},
        {"kind": "people"},
        {"field": "x" * 50},
        {"field": "other"},
    ],
)
def test_bad_params_are_422(
    public_client: TestClient, public_headers: dict[str, str], params: dict[str, Any]
) -> None:
    assert public_client.get(URL, params=params, headers=public_headers).status_code == 422


def test_views_are_served_from_the_reader_cache(
    public_client: TestClient,
    public_headers: dict[str, str],
    redis_client: redis.Redis,
    db_session: Session,
) -> None:
    public_client.app.dependency_overrides[domain_cache.cache_client] = lambda: redis_client  # type: ignore[attr-defined]
    stat(db_session, AS_OF, 3)
    variants = [
        {"tab": "trends"},
        {"tab": "trends", "period": "week"},
        {"tab": "documents", "field": "ai"},
        {"tab": "documents", "company": "openai"},
        {"tab": "documents", "org": "KAIST"},
        {"tab": "documents", "page": 2},
        {"tab": "companies", "kind": "org"},
    ]

    first = [public_client.get(URL, params=p, headers=public_headers) for p in variants]
    second = [public_client.get(URL, params=p, headers=public_headers) for p in variants]
    bad = public_client.get(URL, params={"field": "nope"}, headers=public_headers)

    assert [r.headers["x-cache"] for r in first] == ["miss"] * len(variants)
    assert [r.headers["x-cache"] for r in second] == ["hit"] * len(variants)
    assert [r.json() for r in first] == [r.json() for r in second]
    assert bad.status_code == 422


def test_warm_fills_the_default_views(
    public_client: TestClient,
    public_headers: dict[str, str],
    redis_client: redis.Redis,
    db_session: Session,
) -> None:
    public_client.app.dependency_overrides[domain_cache.cache_client] = lambda: redis_client  # type: ignore[attr-defined]
    stat(db_session, AS_OF, 3)

    warmed = domain_cache.warm(db_session, now=at(NOW_DAY), client=redis_client)

    assert warmed == 30
    hit = public_client.get(URL, params={"period": "week"}, headers=public_headers)
    assert hit.headers["x-cache"] == "hit"
    patents = public_client.get(
        "/api/public/patents", params={"tab": "documents"}, headers=public_headers
    )
    assert patents.headers["x-cache"] == "hit"


def insight(
    session: Session,
    day: date,
    *,
    kind: InsightKind = InsightKind.RESEARCH,
    status: InsightStatus = InsightStatus.PUBLISHED,
    text: str = "AI 논문이 늘었다.",
) -> DomainInsightRecord:
    row = DomainInsightRecord(
        insight_date=day,
        kind=kind,
        status=status,
        model="claude-opus-5-5",
        payload={
            "as_of": (day - timedelta(days=1)).isoformat(),
            "overview": [{"text": text, "doc_ids": [11, 12]}, {"text": "둘째.", "doc_ids": []}],
            "fields": [
                {"field": "ai", "text": "AI 한 줄.", "doc_ids": [11]},
                {"field": "semis", "text": "반도체 한 줄.", "doc_ids": []},
            ],
            "companies": [{"company_key": "openai", "text": "OpenAI 한 줄.", "doc_ids": [12]}],
            "watch": "관심 기업 한 줄.",
        },
        generated_at=at(day, 5),
    )
    session.add(row)
    session.flush()
    return row


def test_tabs_show_the_latest_published_insight_with_its_date(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    stat(db_session, AS_OF, 3)
    assert get(public_client, public_headers)["overview"]["insight"] is None
    insight(db_session, date(2026, 10, 2), text="그제.")
    insight(db_session, AS_OF, text="어제.")
    insight(db_session, NOW_DAY, status=InsightStatus.FAILED, text="오늘 실패.")
    insight(db_session, NOW_DAY + timedelta(days=1), text="내일.")  # not yet: dated tomorrow
    insight(db_session, NOW_DAY, kind=InsightKind.PATENT, text="특허.")

    overview = get(public_client, public_headers)["overview"]["insight"]
    fields = get(public_client, public_headers, tab="fields", field="ai")["fields"]["detail"]
    companies = get(public_client, public_headers, tab="companies")["companies"]["insight"]
    patents = public_client.get("/api/public/patents", headers=public_headers).json()

    assert overview == {
        "date": "2026-10-03",
        "sentences": [
            {"text": "어제.", "doc_ids": [11, 12], "key": None},
            {"text": "둘째.", "doc_ids": [], "key": None},
        ],
    }
    assert fields["insight"] == {
        "date": "2026-10-03",
        "sentences": [{"text": "AI 한 줄.", "doc_ids": [11], "key": "ai"}],
    }
    assert companies["sentences"] == [
        {"text": "관심 기업 한 줄.", "doc_ids": [], "key": None},
        {"text": "OpenAI 한 줄.", "doc_ids": [12], "key": "openai"},
    ]
    assert patents["overview"]["insight"]["date"] == "2026-10-04"
    assert patents["overview"]["insight"]["sentences"][0]["text"] == "특허."
    quiet = get(public_client, public_headers, tab="fields", field="health_tech")
    assert quiet["fields"]["detail"]["insight"] is None  # no line for the field


def test_a_new_insight_starts_new_cache_keys(
    public_client: TestClient,
    public_headers: dict[str, str],
    redis_client: redis.Redis,
    db_session: Session,
) -> None:
    public_client.app.dependency_overrides[domain_cache.cache_client] = lambda: redis_client  # type: ignore[attr-defined]
    stat(db_session, AS_OF, 3)
    insight(db_session, AS_OF, text="어제.")

    def fetch(**params: Any) -> Any:
        return public_client.get(URL, params=params, headers=public_headers)

    first, trends = fetch(), fetch(tab="trends")
    assert first.headers["x-cache"] == "miss"
    assert fetch().headers["x-cache"] == "hit"
    insight(db_session, NOW_DAY, text="오늘.")

    fresh = fetch()
    assert fresh.headers["x-cache"] == "miss"
    assert fresh.json()["overview"]["insight"]["sentences"][0]["text"] == "오늘."
    assert fetch().headers["x-cache"] == "hit"
    assert trends.headers["x-cache"] == "miss"
    assert fetch(tab="trends").headers["x-cache"] == "hit"  # tabs without an insight keep theirs
