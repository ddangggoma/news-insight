import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.public import facts
from tests.public.seed import seed_corpus

pytestmark = pytest.mark.db


def visible(session: Session) -> set[int]:
    return set(session.scalars(select(facts.F.item_id)))


def test_the_view_holds_ready_cards_and_changes_only_on_refresh(db_session: Session) -> None:
    ids = seed_corpus(db_session)
    assert visible(db_session) == set()  # created empty-handed by the migration in tests

    facts.refresh(db_session)
    shown = visible(db_session)
    assert ids["Galaxy agent OS"] in shown
    assert ids["Failed card"] not in shown  # not ready
    ready = db_session.scalar(
        select(func.count()).select_from(ItemCard).where(ItemCard.status == CardStatus.READY)
    )
    assert len(shown) == ready

    card = db_session.scalars(
        select(ItemCard).where(ItemCard.item_id == ids["Galaxy agent OS"])
    ).one()
    card.status = CardStatus.FAILED
    db_session.flush()
    assert ids["Galaxy agent OS"] in visible(db_session)  # until the next refresh

    facts.refresh(db_session)
    assert ids["Galaxy agent OS"] not in visible(db_session)
    # the swapped-in view keeps the migration's index names, and no spare view is left
    indexes = set(
        db_session.scalars(
            text("SELECT indexname FROM pg_indexes WHERE tablename LIKE 'reader_facts%'")
        )
    )
    assert indexes == {"uq_reader_facts_item_id", "ix_reader_facts_occurred_at"}


def test_the_scheduler_refreshes_the_view_every_three_minutes() -> None:
    from news_insight.jobs import tasks  # noqa: F401 - registers the task
    from news_insight.jobs.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["reader-refresh-facts"]
    assert entry["task"] == "reader.refresh_facts"
    assert entry["schedule"] == 180.0
    assert entry["options"]["expires"] < entry["schedule"]
    assert "reader.refresh_facts" in celery_app.tasks
