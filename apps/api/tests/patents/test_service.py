"""patents.index: EPS pilot, OPS and patent-news items → patent_meta."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item, ItemDedup
from news_insight.patents.models import PatentMeta, PatentSource
from news_insight.patents.service import index_patents
from news_insight.sources.enums import Track
from tests.documents import SEEN, card, document, source

pytestmark = pytest.mark.db

NOW = SEEN + timedelta(hours=1)


def meta(session: Session, item_id: int) -> PatentMeta:
    row = session.get(PatentMeta, item_id)
    assert row is not None
    return row


def eps(session: Session, slug: str, summary: str, **kwargs: object) -> int:
    src = source(
        session,
        "epo-publication-server",
        category="patent_office",
        config={"mode": "epo_publications"},
    )
    number = f"EP48157{slug}NWA1"
    item = document(
        session,
        src,
        slug,
        stable_id=f"epo:{number}",
        summary=f"{number}; {summary}",
        author="European Patent Office",
        **kwargs,  # type: ignore[arg-type]
    )
    return item.id


def test_eps_pilot_items_take_ipc_and_field_from_the_summary(db_session: Session) -> None:
    item_id = eps(db_session, "26", "IPC: H01M 10/052, G06N 3/08, A01K 1/02")

    result = index_patents(db_session, now=NOW)

    assert (result.indexed, result.removed) == (1, 0)
    row = meta(db_session, item_id)
    assert (row.publication_number, row.kind, row.office) == ("EP4815726", "A1", "EP")
    assert row.source == PatentSource.EPS
    assert row.ipc == ["H01M 10/052", "G06N 3/08", "A01K 1/02"] and row.cpc == []
    assert (row.field, row.fields) == ("energy", ["energy", "ai"])
    assert row.applicants == [] and row.company_keys == []  # the author is the office
    assert row.indexed_at == NOW


def test_unmapped_codes_fall_back_to_the_card_field_then_other(db_session: Session) -> None:
    carded = eps(db_session, "27", "IPC: A01K 13/00")
    plain = eps(db_session, "28", "IPC: A01N 25/02")
    card(db_session, db_session.get_one(Item, carded), field="health_tech", signal_type="ip")

    index_patents(db_session, now=NOW)

    assert (meta(db_session, carded).field, meta(db_session, carded).fields) == (
        "health_tech",
        ["health_tech"],
    )
    assert meta(db_session, plain).field == "other"


def test_ops_items_take_applicants_and_the_query_classification(db_session: Session) -> None:
    src = source(
        db_session,
        "epo-ops-us-ai",
        category="patent_office",
        config={"mode": "epo_ops", "cql": "pn=US and cpc=G06N and pd>={today-30d}"},
    )
    item = document(
        db_session,
        src,
        "ops",
        stable_id="US2026123456A1",
        summary="A neural network accelerator.",
        author="SAMSUNG ELECTRONICS CO LTD; Unknown Labs LLC",
    )
    card(db_session, item, field="semis", signal_type="ip", companies=["NVIDIA"])

    index_patents(db_session, now=NOW)

    row = meta(db_session, item.id)
    assert row.source == PatentSource.OPS
    assert (row.publication_number, row.kind, row.office) == ("US2026123456", "A1", "US")
    assert row.applicants == ["SAMSUNG ELECTRONICS CO LTD", "Unknown Labs LLC"]
    assert row.company_keys == ["samsungelectronics", "nvidia"]  # applicants, then the card
    assert row.cpc == ["G06N"] and (row.field, row.fields) == ("ai", ["ai"])


def test_ip_news_takes_card_field_companies_and_a_cited_patent(db_session: Session) -> None:
    news = source(db_session, "ipwatchdog-web", category="ip_office", track=Track.NEWS)
    item = document(db_session, news, "suit", refs=(("patent", "US12264976"),))
    card(db_session, item, field="display_av", signal_type="ip", companies=["Apple", "LG Display"])
    other = document(db_session, news, "not-ip")
    card(db_session, other, field="ai", signal_type="market")

    result = index_patents(db_session, now=NOW)

    assert result.indexed == 1
    row = meta(db_session, item.id)
    assert row.source == PatentSource.NEWS
    assert (row.publication_number, row.office, row.kind) == ("US12264976", "US", None)
    assert (row.field, row.company_keys) == ("display_av", ["apple", "lgdisplay"])
    assert db_session.get(PatentMeta, other.id) is None


def test_reindexes_after_a_new_card_and_drops_news_that_is_no_longer_ip(
    db_session: Session,
) -> None:
    news = source(db_session, "ipwatchdog-web", category="ip_office", track=Track.NEWS)
    item = document(db_session, news, "suit")
    news_card = card(db_session, item, field="display_av", signal_type="ip")
    index_patents(db_session, now=NOW)
    assert index_patents(db_session, now=NOW + timedelta(hours=1)).indexed == 0  # nothing new

    news_card.field = "semis"
    news_card.generated_at = NOW + timedelta(minutes=30)
    db_session.flush()
    assert index_patents(db_session, now=NOW + timedelta(hours=1)).indexed == 1
    assert meta(db_session, item.id).field == "semis"

    news_card.signal_type = "market"
    news_card.generated_at = NOW + timedelta(hours=2)
    db_session.flush()
    result = index_patents(db_session, now=NOW + timedelta(hours=3))
    assert (result.indexed, result.removed) == (0, 1)
    assert db_session.get(PatentMeta, item.id) is None


def test_skips_repeats_and_canaries_and_respects_the_limit(db_session: Session) -> None:
    first = eps(db_session, "30", "IPC: H04W 72/04")
    newest = eps(db_session, "31", "IPC: H04W 72/04", published=SEEN + timedelta(days=1))
    repeat = eps(db_session, "32", "IPC: H04W 72/04")
    dedup = db_session.get(ItemDedup, repeat)
    assert dedup is not None
    dedup.duplicate_of = first
    eps(db_session, "33", "IPC: H04W 72/04", canary=True)
    db_session.flush()

    assert index_patents(db_session, now=NOW, limit=1).indexed == 1
    assert db_session.scalars(select(PatentMeta.item_id)).all() == [newest]
    index_patents(db_session, now=NOW)
    assert set(db_session.scalars(select(PatentMeta.item_id))) == {newest, first}


def test_news_takes_the_patent_its_text_cites_first(db_session: Session) -> None:
    news = source(db_session, "ipwatchdog-web", category="ip_office", track=Track.NEWS)
    item = document(
        db_session,
        news,
        "kr",
        title="Court construes KR 10-2025-0012345 claims",
        summary="The ruling also cites US12264976 and EP 4123456 A1.",
        refs=(("patent", "EP4123456"), ("patent", "KR10-2025-0012345"), ("patent", "US12264976")),
    )
    card(db_session, item, field="semis", signal_type="ip")

    index_patents(db_session, now=NOW)

    row = meta(db_session, item.id)
    assert (row.publication_number, row.office) == ("KR1020250012345", "KR")
