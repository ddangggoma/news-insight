"""Daily research and patent counts: KST days, breakdowns, idempotent rebuilds."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item, ItemDedup
from news_insight.insights.stats import (
    day_bounds,
    recent_days,
    recompute_days,
    recompute_recent,
)
from news_insight.patents.models import PatentDailyStat
from news_insight.patents.service import index_patents
from news_insight.research.models import EnrichStatus, ResearchDailyStat, ResearchMeta
from news_insight.sources.enums import Track
from tests.documents import card, document, source

pytestmark = pytest.mark.db

DAY = date(2026, 11, 2)
LATE = datetime(2026, 11, 2, 14, 59, 59, tzinfo=UTC)  # 23:59:59 KST on the 2nd
MIDNIGHT = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)  # 00:00 KST on the 3rd


def research_rows(session: Session, day: date = DAY) -> set[tuple[object, ...]]:
    return {
        (
            r.dim,
            r.field,
            r.theme,
            r.company_key,
            r.org_name,
            r.org_type,
            r.country,
            r.n,
            r.n_company,
        )
        for r in session.scalars(select(ResearchDailyStat).where(ResearchDailyStat.day == day))
    }


def patent_rows(session: Session, day: date = DAY) -> set[tuple[object, ...]]:
    return {
        (r.dim, r.field, r.source, r.company_key, r.office, r.n)
        for r in session.scalars(select(PatentDailyStat).where(PatentDailyStat.day == day))
    }


def enriched(
    session: Session,
    item: Item,
    *,
    institutions: list[dict[str, object]],
    countries: list[str],
    company_keys: list[str],
) -> None:
    session.add(
        ResearchMeta(
            item_id=item.id,
            doi=f"10.1/{item.id}",
            institutions=institutions,
            countries=countries,
            company_keys=company_keys,
            has_company=any(i["type"] == "company" for i in institutions),
            status=EnrichStatus.OK,
            enriched_at=MIDNIGHT,
        )
    )
    session.flush()


def inst(name: str, kind: str, country: str, key: str | None = None) -> dict[str, object]:
    return {"name": name, "type": kind, "country": country, "ror": None, "company_key": key}


def test_day_bounds_are_kst_midnights() -> None:
    assert day_bounds(DAY) == (
        datetime(2026, 11, 1, 15, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 15, 0, tzinfo=UTC),
    )


def test_recent_days_are_yesterday_and_the_two_before_in_kst() -> None:
    # 2026-11-04 01:00 KST is still 2026-11-03 in UTC
    now = datetime(2026, 11, 3, 16, 0, tzinfo=UTC)

    assert recent_days(now) == [date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)]


def test_research_breakdowns_by_field_theme_company_org_and_country(
    db_session: Session,
) -> None:
    src = source(db_session, "arxiv-cs")
    google = document(db_session, src, "google", published=LATE)
    card(db_session, google, field="ai", themes=["ai__foundation_models", "semis__ap_soc_npu"])
    enriched(
        db_session,
        google,
        institutions=[
            inst("Google (United States)", "company", "US", "google"),
            inst("Tiny Startup (United States)", "company", "US"),
            inst("University of Toronto", "education", "CA"),
        ],
        countries=["CA", "US"],
        company_keys=["google"],
    )
    uni = document(db_session, src, "uni", published=None, seen=LATE - timedelta(hours=3))
    card(db_session, uni, field="ai", themes=["ai__foundation_models"])
    enriched(
        db_session,
        uni,
        institutions=[inst("University of Toronto", "education", "CA")],
        countries=["CA"],
        company_keys=[],
    )
    plain = document(db_session, src, "no-card", published=LATE - timedelta(hours=1))
    document(db_session, src, "next-day", published=MIDNIGHT)

    recompute_days(db_session, [DAY])

    assert research_rows(db_session) == {
        ("total", "ai", "", "", "", "", "", 2, 1),
        ("total", "other", "", "", "", "", "", 1, 0),
        ("theme", "ai", "ai__foundation_models", "", "", "", "", 2, 1),
        ("theme", "semis", "semis__ap_soc_npu", "", "", "", "", 1, 1),
        ("company", "ai", "", "google", "", "", "", 1, 1),
        ("org", "ai", "", "", "Tiny Startup (United States)", "company", "", 1, 1),
        ("org", "ai", "", "", "University of Toronto", "education", "", 2, 1),
        ("country", "ai", "", "", "", "", "CA", 2, 1),
        ("country", "ai", "", "", "", "", "US", 1, 1),
    }
    assert plain.id  # counted under "other": a paper without a card still counts
    assert research_rows(db_session, DAY + timedelta(days=1)) == set()  # not asked for


def test_research_counts_skip_patents_repeats_canaries_and_archive_pages(
    db_session: Session,
) -> None:
    src = source(db_session, "arxiv-cs")
    keep = document(db_session, src, "keep", published=LATE)
    repeat = document(db_session, src, "repeat", published=LATE)
    dedup = db_session.get(ItemDedup, repeat.id)
    assert dedup is not None
    dedup.duplicate_of = keep.id
    document(db_session, src, "canary", published=LATE, canary=True)
    document(db_session, src, "archive", published=LATE, seen=LATE + timedelta(days=40))
    office = source(db_session, "epo", category="patent_office")
    document(db_session, office, "patent", published=LATE)
    news = source(db_session, "news", category="independent_media", track=Track.NEWS)
    document(db_session, news, "news", published=LATE)
    db_session.flush()

    recompute_days(db_session, [DAY])

    assert research_rows(db_session) == {("total", "other", "", "", "", "", "", 1, 0)}


def test_patent_breakdowns_by_field_source_company_and_office(db_session: Session) -> None:
    eps = source(db_session, "epo", category="patent_office", config={"mode": "epo_publications"})
    document(
        db_session,
        eps,
        "eps",
        stable_id="epo:EP4815724NWA1",
        summary="EP4815724NWA1; IPC: H01M 10/052",
        published=LATE,
    )
    news = source(db_session, "ipwatchdog", category="ip_office", track=Track.NEWS)
    suit = document(db_session, news, "suit", published=LATE, refs=(("patent", "US12264976"),))
    card(db_session, suit, field="display_av", signal_type="ip", companies=["Apple"])
    later = document(db_session, news, "later", published=MIDNIGHT)
    card(db_session, later, field="ai", signal_type="ip")
    index_patents(db_session, now=MIDNIGHT)

    recompute_days(db_session, [DAY])

    assert patent_rows(db_session) == {
        ("total", "energy", "eps", "", "", 1),
        ("office", "energy", "eps", "", "EP", 1),
        ("total", "display_av", "news", "", "", 1),
        ("company", "display_av", "news", "apple", "", 1),
        ("office", "display_av", "news", "", "US", 1),
    }


def test_recompute_is_idempotent_and_follows_changes(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    paper = document(db_session, src, "p", published=LATE)
    paper_card = card(db_session, paper, field="ai", themes=[])

    first = recompute_days(db_session, [DAY])
    again = recompute_days(db_session, [DAY])
    assert first == again and first.research_rows == 1
    assert research_rows(db_session) == {("total", "ai", "", "", "", "", "", 1, 0)}

    paper_card.field = "semis"
    db_session.flush()
    recompute_days(db_session, [DAY])
    assert research_rows(db_session) == {("total", "semis", "", "", "", "", "", 1, 0)}


def test_recompute_recent_rebuilds_three_days(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    for days_ago in range(5):
        document(db_session, src, f"d{days_ago}", published=LATE - timedelta(days=days_ago))

    result = recompute_recent(db_session, now=MIDNIGHT + timedelta(hours=4))

    assert result.days == [DAY - timedelta(days=2), DAY - timedelta(days=1), DAY]
    stored = set(db_session.scalars(select(ResearchDailyStat.day)))
    assert stored == set(result.days)


def test_recent_rebuild_also_covers_days_of_papers_enriched_since_the_last_run(
    db_session: Session,
) -> None:
    now = MIDNIGHT + timedelta(days=5, hours=4)  # 04:00 KST on 2026-11-08
    old_day = DAY - timedelta(days=1)  # a week before "now" in KST, outside the last three
    src = source(db_session, "arxiv-cs")
    paper = document(db_session, src, "late", published=LATE - timedelta(days=1))
    card(db_session, paper, field="ai", themes=[])
    recompute_days(db_session, [old_day])
    assert research_rows(db_session, old_day) == {("total", "ai", "", "", "", "", "", 1, 0)}

    enriched(
        db_session,
        paper,
        institutions=[inst("Google (United States)", "company", "US", "google")],
        countries=["US"],
        company_keys=["google"],
    )
    db_session.get_one(ResearchMeta, paper.id).enriched_at = now - timedelta(hours=2)
    stale = document(db_session, src, "stale", published=LATE - timedelta(days=2))
    db_session.add(
        ResearchMeta(
            item_id=stale.id,
            doi="10.1/stale",
            status=EnrichStatus.OK,
            enriched_at=now - timedelta(days=3),
        )
    )
    db_session.flush()

    result = recompute_recent(db_session, now=now)

    assert old_day in result.days and DAY - timedelta(days=2) not in result.days
    assert research_rows(db_session, old_day) == {
        ("total", "ai", "", "", "", "", "", 1, 1),
        ("company", "ai", "", "google", "", "", "", 1, 1),
        ("country", "ai", "", "", "", "", "US", 1, 1),
    }


def test_recent_rebuild_leaves_today_out_even_when_it_changed(db_session: Session) -> None:
    src = source(db_session, "arxiv-cs")
    now = MIDNIGHT + timedelta(hours=4)  # 04:00 KST on the 3rd
    paper = document(db_session, src, "today", published=MIDNIGHT + timedelta(hours=1))
    enriched(db_session, paper, institutions=[], countries=["KR"], company_keys=[])

    result = recompute_recent(db_session, now=now)

    assert DAY + timedelta(days=1) not in result.days
