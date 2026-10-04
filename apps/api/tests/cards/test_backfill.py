from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.backfill import relink_keywords, run_classify, unclassified_count
from news_insight.cards.engines import EngineError, EngineOutput, Quota
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.cards.schemas import LabelInput
from news_insight.cards.service import CardPolicy, SessionScope
from news_insight.classify.keywords import AliasSeed
from news_insight.classify.models import ItemKeyword, ItemLabel, Keyword
from news_insight.classify.store import current_labels
from news_insight.classify.taxonomy import Axis, get_taxonomy
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 4, 3, tzinfo=UTC)
POLICY = CardPolicy(agy_batch=2, qwen_batch=1, time_budget_seconds=1000)
REV = get_taxonomy().revision
SEED = AliasSeed(by_key={"ondeviceai": "온디바이스 AI", "온디바이스ai": "온디바이스 AI"})


class FakeLabeler:
    def __init__(
        self, name: str, *, fail: Exception | None = None, skip: frozenset[int] = frozenset()
    ) -> None:
        self.name, self.fail, self.skip = name, fail, skip
        self.batches: list[list[LabelInput]] = []

    def classify(self, inputs: list[LabelInput]) -> EngineOutput:
        self.batches.append(inputs)
        if self.fail:
            raise self.fail
        labels = [
            {"id": c.id, "fields": ["display", "bogus"], "products": [], "impact": "watch"}
            for c in inputs
            if c.id not in self.skip
        ]
        return EngineOutput(raw={"labels": labels}, model=f"{self.name}-model")


class FakeAgyLabeler(FakeLabeler):
    def __init__(self, quota: Quota, **kwargs: Any) -> None:
        super().__init__("agy", **kwargs)
        self.quota = quota

    def usage(self) -> Quota:
        return self.quota


def scope_for(db_session: Session) -> SessionScope:
    @contextmanager
    def scope() -> Iterator[Session]:
        with db_session.begin_nested():
            yield db_session

    return scope


def seed_cards(db_session: Session, titles: list[str]) -> dict[str, ItemCard]:
    """Ready cards made before classification existed (taxonomy_rev NULL)."""
    source = build_source()
    db_session.add(source)
    db_session.flush()
    ingest_items(
        db_session,
        source,
        [RawItem(stable_id=t, url=f"https://www.example.com/{t}", title=t) for t in titles],
        fetch_run=None,
        now=NOW,
        canary=True,
    )
    made: dict[str, ItemCard] = {}
    for item in db_session.scalars(select(Item)):
        card = ItemCard(
            item_id=item.id,
            status=CardStatus.READY,
            title_ko=f"{item.title} 한국어",
            summary_ko=["요약"],
            keywords=["온디바이스AI", "On-device AI", "패널"],
            engine="agy",
            model="gemini",
            input_hash=item.content_hash,
            attempts=0,
            taxonomy_rev=None,
            generated_at=NOW,
        )
        db_session.add(card)
        made[item.title] = card
    db_session.flush()
    return made


def test_backfill_classifies_unlabeled_cards_from_title_and_summary(db_session: Session) -> None:
    made = seed_cards(db_session, ["a", "b", "c"])
    agy = FakeAgyLabeler(Quota(weekly=80, five_hour=60))

    stats = run_classify(scope_for(db_session), agy=agy, qwen=None, policy=POLICY, limit=None)

    assert stats.ready == 3 and stats.batches == {"agy": 2}
    assert agy.batches[0][0].title.endswith("한국어") and agy.batches[0][0].summary == ["요약"]
    item_id = made["a"].item_id
    assert current_labels(db_session, [item_id])[item_id] == {
        Axis.FIELD: ["display"],
        Axis.PRODUCT: [],
        Axis.IMPACT: ["watch"],
    }
    assert {card.taxonomy_rev for card in made.values()} == {REV}
    assert {row.engine for row in db_session.scalars(select(ItemLabel))} == {"agy"}
    assert unclassified_count(db_session, REV) == 0

    again = run_classify(scope_for(db_session), agy=agy, qwen=None, policy=POLICY, limit=None)

    assert again.ready == 0 and again.batches == {}


def test_backfill_respects_limit_quota_fallback_and_current_revision(db_session: Session) -> None:
    made = seed_cards(db_session, ["a", "b", "c"])
    made["c"].taxonomy_rev = REV  # already classified at the current revision
    made["b"].taxonomy_rev = REV - 1 if REV > 1 else None  # older revision: classify again
    db_session.flush()
    agy = FakeAgyLabeler(Quota(weekly=5, five_hour=60))  # reserved: go straight to qwen
    qwen = FakeLabeler("qwen")

    stats = run_classify(scope_for(db_session), agy=agy, qwen=qwen, policy=POLICY, limit=1)

    assert agy.batches == [] and stats.batches == {"qwen": 1} and stats.ready == 1
    assert unclassified_count(db_session, REV) == 1
    assert any("qwen" in note for note in stats.notes)


def test_backfill_skips_items_the_engine_left_out_and_stops_when_qwen_is_down(
    db_session: Session,
) -> None:
    made = seed_cards(db_session, ["a", "b"])
    left_out = made["a"].item_id
    qwen = FakeLabeler("qwen", skip=frozenset({left_out}))

    stats = run_classify(scope_for(db_session), agy=None, qwen=qwen, policy=POLICY, limit=None)

    assert (stats.ready, stats.failed) == (1, 1)
    assert made["a"].taxonomy_rev is None and len(qwen.batches) == 2

    down = run_classify(
        scope_for(db_session),
        agy=None,
        qwen=FakeLabeler("qwen", fail=EngineError("down")),
        policy=POLICY,
        limit=None,
    )

    assert down.ready == 0 and down.notes == ["down"]


def test_relink_normalises_existing_card_keywords_without_an_engine(db_session: Session) -> None:
    made = seed_cards(db_session, ["a", "b"])

    linked = relink_keywords(scope_for(db_session), seed=SEED, limit=None, relink_all=False)
    again = relink_keywords(scope_for(db_session), seed=SEED, limit=None, relink_all=False)
    forced = relink_keywords(scope_for(db_session), seed=SEED, limit=1, relink_all=True)

    assert (linked, again, forced) == (2, 0, 1)
    names = db_session.scalars(
        select(Keyword.canonical)
        .join(ItemKeyword, ItemKeyword.keyword_id == Keyword.id)
        .where(ItemKeyword.item_id == made["a"].item_id)
        .order_by(Keyword.canonical)
    )
    assert list(names) == ["온디바이스 AI", "패널"]
