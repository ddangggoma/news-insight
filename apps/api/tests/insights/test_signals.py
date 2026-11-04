"""Per-paper signals of the 주목 문헌 list (insights/signals.py)."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import ItemDedup
from news_insight.insights.signals import canon_key, citation_growth, recompute_signals
from news_insight.research.models import ResearchSignal
from news_insight.sources.enums import Track
from tests.documents import card, document, source

THROUGH = date(2026, 11, 2)
LATE = datetime(2026, 11, 2, 14, 0, tzinfo=UTC)  # 23:00 KST on the 2nd
AFTER = datetime(2026, 11, 2, 15, 30, tzinfo=UTC)  # 00:30 KST on the 3rd


def test_canon_keys_join_arxiv_ids_and_their_dois() -> None:
    assert canon_key("10.48550/arXiv.2610.00001v3") == "arxiv:2610.00001"
    assert canon_key("10.48550/arxiv.2610.00001") == "arxiv:2610.00001"
    assert canon_key("10.1038/S41586-021-03819-2") == "doi:10.1038/s41586-021-03819-2"
    assert canon_key(None) is None


def test_citation_growth_is_this_year_against_last() -> None:
    counts = [{"year": 2025, "cited_by_count": 4}, {"year": 2026, "cited_by_count": 10}]
    assert citation_growth(counts, 2026) == 6
    assert citation_growth(counts, 2027) == 0  # nothing yet this year
    assert citation_growth([{"year": 2026, "cited_by_count": 1}], 2026) == 1
    assert citation_growth(None, 2026) == 0


@pytest.mark.db
def test_mentions_count_eligible_items_up_to_the_end_of_through(db_session: Session) -> None:
    papers = source(db_session, "arxiv")
    news = source(db_session, "verge", category="independent_media", track=Track.NEWS)
    paper = document(
        db_session,
        papers,
        "p",
        url="https://arxiv.org/abs/2611.00001",
        refs=(("arxiv", "2611.00001"),),
        published=LATE,
        seen=LATE,
    )
    card(db_session, paper, field="semis")
    cites = (("doi", "10.48550/arxiv.2611.00001"),)
    document(db_session, news, "a", refs=cites, published=LATE, seen=LATE)
    repeat = document(db_session, news, "b", refs=cites, published=LATE, seen=LATE)
    first = document(db_session, news, "c", published=LATE, seen=LATE)
    dedup = db_session.get(ItemDedup, repeat.id)
    assert dedup is not None
    dedup.duplicate_of, dedup.matched_by = first.id, "title"
    document(db_session, news, "d", refs=cites, published=AFTER, seen=AFTER)  # after through
    db_session.flush()

    result = recompute_signals(db_session, through=THROUGH, now=AFTER)

    row = db_session.scalars(select(ResearchSignal).where(ResearchSignal.item_id == paper.id)).one()
    assert result.rows == 1 and row.lead and row.lead_id == paper.id
    assert (row.mentions, row.field, row.day, row.canon_key) == (
        1,
        "semis",
        THROUGH,
        "arxiv:2611.00001",
    )
    assert row.score == pytest.approx(10.0)
