from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.engines import EngineError, EngineOutput, Quota, QuotaExhausted
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.cards.schemas import CardInput, ClassifyInput
from news_insight.cards.service import (
    MAX_ATTEMPTS,
    MAX_CLASSIFY_ATTEMPTS,
    CardPolicy,
    SessionScope,
    classify_pending_count,
    pending_count,
    pending_items,
    run_cards,
)
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import StorageRight
from news_insight.sources.models import Source
from news_insight.taxonomy.catalog import TAXONOMY_REVISION
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
        self.classified: list[list[int]] = []
        self.classify_fail: Exception | None = None

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

    def classify(self, inputs: list[ClassifyInput]) -> EngineOutput:
        self.classified.append([entry.id for entry in inputs])
        if self.classify_fail:
            raise self.classify_fail
        cards = [
            {
                "id": entry.id,
                "field": "ai",
                "themes": ["ai__ai_agents"],
                "scope": "dx",
                "relevance": 70,
                "topic_candidates": ["위성 직접통신", "  위성  직접통신 "],
            }
            for entry in inputs
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
    source = db_session.scalars(select(Source).where(Source.key == "example-news")).first()
    if source is None:
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


def test_without_qwen_a_spent_quota_waits_for_the_next_run(db_session: Session) -> None:
    seed(db_session, ["a", "b", "c"])
    agy = FakeAgy([FULL, SPENT])

    stats = run_cards(scope_for(db_session), agy=agy, qwen=None, policy=POLICY)

    assert stats.batches == {"agy": 1} and pending_count(db_session) == 1
    assert any("waiting for the next run" in note for note in stats.notes)
    assert not any("qwen" in note for note in stats.notes)


class FlakyAgy(FakeAgy):
    """Fails the first `failures` calls, then works."""

    def __init__(self, failures: int) -> None:
        super().__init__([FULL])
        self.failures = failures

    def generate(self, inputs: list[CardInput]) -> EngineOutput:
        if self.failures:
            self.failures -= 1
            self.batches.append([card.id for card in inputs])
            raise EngineError("agy returned no structured output")
        return super().generate(inputs)


def test_without_qwen_a_failed_batch_is_retried_on_agy(db_session: Session) -> None:
    seed(db_session, ["a", "b"])
    agy = FlakyAgy(failures=1)

    stats = run_cards(scope_for(db_session), agy=agy, qwen=None, policy=POLICY)

    assert stats.ready == 2 and len(agy.batches) == 2
    assert {card.engine for card in cards(db_session).values()} == {"agy"}


def test_one_malformed_lane_does_not_drop_agy_for_the_run(db_session: Session) -> None:
    """2026-10-10: a single bad answer among parallel lanes sent the rest of the run to Qwen."""
    seed(db_session, ["a", "b", "c", "d"])
    agy = FlakyAgy(failures=1)
    qwen = FakeEngine("qwen")
    policy = CardPolicy(agy_batch=1, agy_parallel=2, qwen_batch=1, time_budget_seconds=1000)

    stats = run_cards(scope_for(db_session), agy=agy, qwen=qwen, policy=policy)

    assert stats.ready == 4 and qwen.batches == []
    assert {card.engine for card in cards(db_session).values()} == {"agy"}


def test_without_qwen_repeated_failures_end_the_run(db_session: Session) -> None:
    seed(db_session, ["a"])
    agy = FlakyAgy(failures=10)

    stats = run_cards(scope_for(db_session), agy=agy, qwen=None, policy=POLICY)

    assert stats.ready == 0 and len(agy.batches) == 2 and pending_count(db_session) == 1


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


def test_older_taxonomy_reclassifies_without_regenerating_text(db_session: Session) -> None:
    seed(db_session, ["a"])
    run_cards(scope_for(db_session), agy=None, qwen=FakeEngine("qwen"), policy=POLICY)
    card = cards(db_session)["a"]
    title_before = card.title_ko
    card.taxonomy_revision = "old"
    db_session.flush()

    assert pending_count(db_session) == 0 and classify_pending_count(db_session) == 1
    qwen = FakeEngine("qwen")
    stats = run_cards(scope_for(db_session), agy=None, qwen=qwen, policy=POLICY)

    assert qwen.batches == [] and len(qwen.classified) == 1
    assert stats.classified == 1 and classify_pending_count(db_session) == 0
    assert card.title_ko == title_before and card.taxonomy_revision == TAXONOMY_REVISION
    assert card.themes == ["ai__ai_agents"]
    assert card.topic_candidates == ["위성 직접통신"]


def test_one_agy_lane_reclassifies_while_new_items_are_carded(db_session: Session) -> None:
    seed(db_session, ["old1", "old2"])
    run_cards(scope_for(db_session), agy=None, qwen=FakeEngine("qwen"), policy=POLICY)
    for card in cards(db_session).values():
        card.taxonomy_revision = "old"
    seed(db_session, ["new1", "new2", "new3", "new4"])
    agy = FakeAgy([FULL])
    policy = CardPolicy(agy_batch=2, agy_parallel=3, classify_batch=10, time_budget_seconds=1000)

    stats = run_cards(scope_for(db_session), agy=agy, qwen=None, policy=policy)

    first_round_cards = agy.batches[:2]
    assert sorted(id for batch in first_round_cards for id in batch) == sorted(
        c.item_id for t, c in cards(db_session).items() if t.startswith("new")
    )
    assert len(agy.classified) == 1 and stats.classified == 2 and stats.ready == 4


def test_qwen_reclassifies_only_after_new_items(db_session: Session) -> None:
    seed(db_session, ["old"])
    run_cards(scope_for(db_session), agy=None, qwen=FakeEngine("qwen"), policy=POLICY)
    cards(db_session)["old"].taxonomy_revision = "old"
    seed(db_session, ["new"])
    qwen = FakeEngine("qwen")
    order: list[str] = []
    qwen.generate = lambda inputs: (order.append("card"), FakeEngine.generate(qwen, inputs))[1]  # type: ignore[method-assign]
    qwen.classify = lambda inputs: (order.append("classify"), FakeEngine.classify(qwen, inputs))[1]  # type: ignore[method-assign]

    run_cards(scope_for(db_session), agy=None, qwen=qwen, policy=POLICY)

    assert order == ["card", "classify"]


def test_classification_gives_up_after_repeated_failures(db_session: Session) -> None:
    seed(db_session, ["a"])
    run_cards(scope_for(db_session), agy=None, qwen=FakeEngine("qwen"), policy=POLICY)
    card = cards(db_session)["a"]
    card.taxonomy_revision, card.field = "old", "ai"
    db_session.flush()

    class Empty(FakeEngine):
        def classify(self, inputs: list[ClassifyInput]) -> EngineOutput:
            return EngineOutput(raw={"cards": []}, model="m")

    for _ in range(MAX_CLASSIFY_ATTEMPTS):
        run_cards(scope_for(db_session), agy=None, qwen=Empty("qwen"), policy=POLICY)

    assert card.taxonomy_revision == TAXONOMY_REVISION and card.field is None
    assert card.error is not None and card.error.startswith("classification gave up")
    assert classify_pending_count(db_session) == 0


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


def test_cards_losing_identifiers_are_rejected_and_retried(db_session: Session) -> None:
    seed(db_session, ["Galaxy S30 launch"])

    class Lossy(FakeEngine):
        def generate(self, inputs: list[CardInput]) -> EngineOutput:
            cards = [
                {"id": c.id, "title_ko": "갤럭시 출시", "summary_ko": [], "keywords": []}
                for c in inputs
            ]
            return EngineOutput(raw={"cards": cards}, model="m")

    run_cards(scope_for(db_session), agy=None, qwen=Lossy("qwen"), policy=POLICY)

    card = cards(db_session)["Galaxy S30 launch"]
    assert card.status is CardStatus.FAILED
    assert card.error == "preservation: lost S30"
    assert pending_count(db_session) == 1


class LossyAgy(FakeAgy):
    """Always drops the model number from the title, and records what it was asked to keep."""

    def __init__(self) -> None:
        super().__init__([FULL])
        self.keeps: list[list[str] | None] = []

    def generate(self, inputs: list[CardInput]) -> EngineOutput:
        self.keeps.extend(card.keep for card in inputs)
        cards = [
            {"id": c.id, "title_ko": "갤럭시 출시", "summary_ko": ["요약"], "keywords": ["k"]}
            for c in inputs
        ]
        return EngineOutput(raw={"cards": cards}, model="agy-model")


def test_retries_name_the_lost_fact_and_the_last_attempt_keeps_the_card(
    db_session: Session,
) -> None:
    seed(db_session, ["Galaxy S30 launch"])
    agy = LossyAgy()
    scope = scope_for(db_session)

    for _ in range(MAX_ATTEMPTS - 1):
        run_cards(scope, agy=agy, qwen=None, policy=POLICY)
    failed = cards(db_session)["Galaxy S30 launch"]
    assert failed.status == CardStatus.FAILED and failed.error == "preservation: lost S30"
    assert agy.keeps == [None, ["S30"]]

    stats = run_cards(scope, agy=agy, qwen=None, policy=POLICY)

    kept = cards(db_session)["Galaxy S30 launch"]
    assert stats.soft == 1 and kept.status == CardStatus.READY
    assert kept.error == "preservation (kept on last attempt): lost S30"
    assert kept.title_ko == "갤럭시 출시"


def test_archive_pages_get_no_card(db_session: Session) -> None:
    from datetime import timedelta

    seed(db_session, ["fresh", "archive"])
    archive = db_session.scalars(select(Item).where(Item.title == "archive")).one()
    archive.published_at = archive.first_seen_at - timedelta(days=400)  # a 2025 page found today
    db_session.flush()

    assert [item.title for item, _ in pending_items(db_session, limit=10)] == ["fresh"]


def test_an_unvalidated_source_waits_after_its_daily_cap(db_session: Session) -> None:
    from news_insight.sources.enums import SourceStatus

    seed(db_session, ["a", "b", "c"])
    source = db_session.scalars(select(Source).where(Source.key == "example-news")).one()
    source.status = SourceStatus.CANDIDATE
    db_session.flush()
    run_cards(
        scope_for(db_session),
        agy=FakeAgy([FULL]),
        qwen=None,
        policy=CardPolicy(agy_batch=2, agy_parallel=1, unvalidated_daily_cap=2),
    )
    assert pending_count(db_session) == 1  # one item left for tomorrow
    assert pending_items(db_session, limit=10, unvalidated_daily_cap=2) == []
    source.status = SourceStatus.ACTIVE
    db_session.flush()
    assert len(pending_items(db_session, limit=10, unvalidated_daily_cap=2)) == 1


def test_same_url_or_same_content_reuses_the_card(db_session: Session) -> None:
    from news_insight.cards.service import REUSED

    seed(db_session, ["original"])
    agy = FakeAgy([FULL])
    run_cards(scope_for(db_session), agy=agy, qwen=None, policy=POLICY)
    original = db_session.scalars(select(Item).where(Item.title == "original")).one()
    other = build_source(key="other-news", storage_right=StorageRight.EXCERPT_ALLOWED)
    db_session.add(other)
    db_session.flush()
    ingest_items(
        db_session,
        other,
        [RawItem(stable_id="copy", url=original.url, title="original (reposted)", summary="x")],
        fetch_run=None,
        now=NOW,
        canary=True,
    )

    stats = run_cards(scope_for(db_session), agy=agy, qwen=None, policy=POLICY)

    copy = cards(db_session)["original (reposted)"]
    assert stats.reused == 1 and len(agy.batches) == 1  # no second engine call
    assert copy.status == CardStatus.READY and copy.engine == REUSED
    assert copy.title_ko == "[agy] original"


class FakeCodex(FakeAgy):
    def __init__(self, quotas: list[Quota], **kwargs: Any) -> None:
        super().__init__(quotas, **kwargs)
        self.name = "codex"


def test_codex_first_then_agy_when_codex_reaches_its_reserve(db_session: Session) -> None:
    seed(db_session, ["a", "b", "c", "d"])
    codex = FakeCodex([FULL, SPENT])
    agy = FakeAgy([FULL])
    policy = CardPolicy(
        agy_batch=2, agy_parallel=1, codex_batch=2, codex_parallel=1, time_budget_seconds=1000
    )

    stats = run_cards(scope_for(db_session), metered=[codex, agy], qwen=None, policy=policy)

    assert stats.batches == {"codex": 1, "agy": 1} and stats.ready == 4
    assert any(
        "codex quota reserved" in note and "switching to agy" in note for note in stats.notes
    )


def test_codex_quota_error_moves_on_and_qwen_comes_last(db_session: Session) -> None:
    seed(db_session, ["a", "b"])
    codex = FakeCodex([FULL], fail=QuotaExhausted("usage limit"))
    agy = FakeAgy([SPENT])
    qwen = FakeEngine("qwen")

    stats = run_cards(scope_for(db_session), metered=[codex, agy], qwen=qwen, policy=POLICY)

    assert stats.batches == {"qwen": 2} and stats.ready == 2
    assert {card.engine for card in cards(db_session).values()} == {"qwen"}


def test_qwen_lanes_run_next_to_codex_when_alongside(db_session: Session) -> None:
    seed(db_session, ["a", "b", "c", "d", "e", "f"])
    codex = FakeCodex([FULL])
    qwen = FakeEngine("qwen")
    policy = CardPolicy(
        codex_batch=2, codex_parallel=1, qwen_batch=1, qwen_parallel=2, time_budget_seconds=1000
    )

    stats = run_cards(
        scope_for(db_session), metered=[codex], qwen=qwen, policy=policy, qwen_alongside=True
    )

    assert stats.ready == 6 and stats.batches["codex"] >= 1 and stats.batches["qwen"] >= 2
    assert len(qwen.batches[0]) == 1 and set(sum(codex.batches, [])).isdisjoint(
        sum(qwen.batches, [])
    )


def test_failing_qwen_lanes_stop_while_codex_goes_on(db_session: Session) -> None:
    seed(db_session, ["a", "b", "c", "d", "e", "f", "g", "h"])
    codex = FakeCodex([FULL])
    qwen = FakeEngine("qwen", fail=EngineError("lm studio down"))
    policy = CardPolicy(codex_batch=2, codex_parallel=1, qwen_batch=1, time_budget_seconds=1000)

    stats = run_cards(
        scope_for(db_session), metered=[codex], qwen=qwen, policy=policy, qwen_alongside=True
    )

    assert len(qwen.batches) == 2 and stats.ready == 8 and pending_count(db_session) == 0
    assert any("qwen lanes stopped" in note for note in stats.notes)
