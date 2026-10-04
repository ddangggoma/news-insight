from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.engines import EngineError, EngineOutput, Quota, QuotaExhausted
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.cards.schemas import CardInput
from news_insight.cards.service import (
    MAX_ATTEMPTS,
    CardPolicy,
    SessionScope,
    pending_count,
    pending_items,
    run_cards,
)
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import StorageRight
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 4, 3, tzinfo=UTC)
POLICY = CardPolicy(agy_batch=2, agy_parallel=1, qwen_batch=1, time_budget_seconds=1000)


class FakeEngine:
    def __init__(
        self, name: str, *, fail: Exception | None = None, skip: frozenset[str] = frozenset()
    ) -> None:
        self.name, self.fail, self.skip = name, fail, skip
        self.batches: list[list[int]] = []

    def generate(self, inputs: list[CardInput]) -> EngineOutput:
        self.batches.append([card.id for card in inputs])
        if self.fail:
            raise self.fail
        cards = [
            {
                "id": c.id,
                "title_ko": f"[{self.name}] {c.title}",
                "summary_ko": ["요약"],
                "keywords": ["k"],
            }
            for c in inputs
            if c.title not in self.skip
        ]
        return EngineOutput(raw={"cards": cards}, model=f"{self.name}-model")


class FakeAgy(FakeEngine):
    def __init__(self, quotas: list[Quota], **kwargs: Any) -> None:
        super().__init__("agy", **kwargs)
        self.quotas = quotas

    def usage(self) -> Quota:
        return self.quotas.pop(0) if len(self.quotas) > 1 else self.quotas[0]


FULL = Quota(weekly=80, five_hour=60)
SPENT = Quota(weekly=9, five_hour=60)


def scope_for(db_session: Session) -> SessionScope:
    @contextmanager
    def scope() -> Iterator[Session]:
        with db_session.begin_nested():
            yield db_session

    return scope


def seed(db_session: Session, titles: list[str]) -> None:
    source = build_source(storage_right=StorageRight.EXCERPT_ALLOWED)
    db_session.add(source)
    db_session.flush()
    ingest_items(
        db_session,
        source,
        [
            RawItem(stable_id=t, url=f"https://www.example.com/{t}", title=t, summary="본문 요약")
            for t in titles
        ],
        fetch_run=None,
        now=NOW,
        canary=True,
    )


def cards(db_session: Session) -> dict[str, ItemCard]:
    rows = db_session.execute(
        select(Item.title, ItemCard).join(ItemCard, ItemCard.item_id == Item.id)
    )
    return {title: card for title, card in rows.tuples()}


def test_agy_generates_all_pending_cards(db_session: Session) -> None:
    seed(db_session, ["a", "b", "c"])
    agy = FakeAgy([FULL])

    stats = run_cards(scope_for(db_session), agy=agy, qwen=FakeEngine("qwen"), policy=POLICY)

    made = cards(db_session)
    assert stats.ready == 3 and stats.batches == {"agy": 2}
    assert {card.engine for card in made.values()} == {"agy"}
    assert made["a"].title_ko == "[agy] a" and made["a"].summary_ko == ["요약"]
    assert pending_count(db_session) == 0


def test_spent_quota_switches_to_qwen(db_session: Session) -> None:
    seed(db_session, ["a", "b", "c"])
    agy = FakeAgy([FULL, SPENT])
    qwen = FakeEngine("qwen")

    stats = run_cards(scope_for(db_session), agy=agy, qwen=qwen, policy=POLICY)

    assert stats.batches == {"agy": 1, "qwen": 1}
    assert {card.engine for card in cards(db_session).values()} == {"agy", "qwen"}
    assert any("qwen" in note for note in stats.notes)


@pytest.mark.parametrize("failure", [QuotaExhausted("quota"), EngineError("crash")])
def test_agy_failure_falls_back_to_qwen(db_session: Session, failure: Exception) -> None:
    seed(db_session, ["a"])
    agy = FakeAgy([FULL], fail=failure)

    stats = run_cards(scope_for(db_session), agy=agy, qwen=FakeEngine("qwen"), policy=POLICY)

    assert stats.ready == 1 and stats.batches == {"qwen": 1}


def test_qwen_outage_leaves_items_pending(db_session: Session) -> None:
    seed(db_session, ["a"])

    stats = run_cards(
        scope_for(db_session),
        agy=None,
        qwen=FakeEngine("qwen", fail=EngineError("down")),
        policy=POLICY,
    )

    assert stats.ready == 0 and pending_count(db_session) == 1
    assert cards(db_session) == {}


def test_missing_cards_retry_then_give_up(db_session: Session) -> None:
    seed(db_session, ["bad"])
    qwen = FakeEngine("qwen", skip=frozenset({"bad"}))

    for _ in range(MAX_ATTEMPTS):
        run_cards(scope_for(db_session), agy=None, qwen=qwen, policy=POLICY)

    card = cards(db_session)["bad"]
    assert (card.status, card.attempts) == (CardStatus.FAILED, MAX_ATTEMPTS)
    assert pending_items(db_session, limit=10) == []


def test_changed_items_are_regenerated(db_session: Session) -> None:
    seed(db_session, ["a"])
    run_cards(scope_for(db_session), agy=None, qwen=FakeEngine("qwen"), policy=POLICY)
    item = db_session.scalars(select(Item)).one()
    item.content_hash = "changed"
    db_session.flush()

    assert pending_count(db_session) == 1


def test_cards_from_an_older_taxonomy_are_regenerated(db_session: Session) -> None:
    seed(db_session, ["a"])
    run_cards(scope_for(db_session), agy=None, qwen=FakeEngine("qwen"), policy=POLICY)
    card = cards(db_session)["a"]
    assert card.taxonomy_revision is not None and pending_count(db_session) == 0

    card.taxonomy_revision = "old"
    db_session.flush()

    assert pending_count(db_session) == 1


def test_agy_lanes_run_batches_concurrently(db_session: Session) -> None:
    import threading
    import time as clock_time

    seed(db_session, [f"t{i}" for i in range(6)])
    active: list[int] = []
    peak = 0
    lock = threading.Lock()

    class SlowAgy(FakeAgy):
        def generate(self, inputs: list[CardInput]) -> EngineOutput:
            nonlocal peak
            with lock:
                active.append(1)
                peak = max(peak, len(active))
            clock_time.sleep(0.05)
            with lock:
                active.pop()
            return super().generate(inputs)

    stats = run_cards(
        scope_for(db_session),
        agy=SlowAgy([FULL]),
        qwen=FakeEngine("qwen"),
        policy=CardPolicy(agy_batch=2, agy_parallel=3, time_budget_seconds=1000),
    )

    assert stats.ready == 6 and stats.batches == {"agy": 3}
    assert peak == 3
