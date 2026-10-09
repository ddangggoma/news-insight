from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard, ItemTriage
from news_insight.cards.service import pending_items
from news_insight.cards.triage import embed_titles, score_pending, title_keys, train
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import SourceStatus
from news_insight.sources.models import Source
from news_insight.stories.models import ItemEmbedding
from news_insight.taxonomy.changes import ChangeSet, apply
from news_insight.taxonomy.seed import seed_taxonomy
from news_insight.technologies.catalog import load_technologies
from news_insight.technologies.service import seed_registry
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime.now(UTC)
_serial = iter(range(100000))
rng = np.random.default_rng(7)


def direction(index: int) -> list[float]:
    vector = rng.normal(0, 0.05, 1024)
    vector[index] += 1.0
    return [float(v) for v in vector / np.linalg.norm(vector)]


def source(db_session: Session, key: str, status: SourceStatus = SourceStatus.ACTIVE) -> Source:
    found = db_session.scalars(select(Source).where(Source.key == key)).one_or_none()
    if found is None:
        found = build_source(key=key, name=key, status=status)
        db_session.add(found)
        db_session.flush()
    return found


def item(db_session: Session, src: Source, title: str, seen: datetime = NOW) -> Item:
    url = f"https://www.example.com/t-{next(_serial)}"
    ingest_items(
        db_session,
        src,
        [RawItem(stable_id=url, url=url, title=title)],
        fetch_run=None,
        now=seen,
        canary=True,
    )
    return db_session.scalars(select(Item).where(Item.url == url)).one()


def carded(db_session: Session, src: Source, dx: bool, theme: str, seen: datetime) -> None:
    it = item(db_session, src, "t", seen)
    db_session.add(
        ItemCard(
            item_id=it.id,
            status=CardStatus.READY,
            title_ko="k",
            summary_ko=[],
            keywords=[],
            input_hash=it.content_hash,
            generated_at=seen,
            scope="dx" if dx else "irrelevant",
            themes=[theme] if dx else [],
        )
    )
    db_session.add(
        # one direction per theme, another for the irrelevant ones
        ItemEmbedding(
            item_id=it.id,
            model="m",
            vector=direction((1 if theme == "ai__ai_agents" else 3) if dx else 2),
            created_at=seen,
        )
    )


@pytest.fixture
def model(db_session: Session) -> int:
    seed_registry(db_session, load_technologies())
    seed_taxonomy(db_session)
    src = source(db_session, "mixed")
    for n in range(700):
        carded(
            db_session,
            src,
            n % 3 != 0,
            "ai__ai_agents" if n % 2 else "semis__ap_soc_npu",
            NOW - timedelta(days=20) + timedelta(minutes=n),
        )
    db_session.flush()
    result = train(db_session, now=NOW)
    assert result is not None and result.auc > 0.95
    return result.model_id


def fake_embed(texts: list[str]) -> list[list[float]]:
    return [direction(1 if "agent" in t.lower() else 3 if "npu" in t.lower() else 2) for t in texts]


def test_scores_order_carding_and_respect_node_priorities(db_session: Session, model: int) -> None:
    good, bad = source(db_session, "good"), source(db_session, "paused", SourceStatus.PAUSED)
    dx = item(db_session, good, "New AI agent framework ships")
    junk = item(db_session, good, "Celebrity gossip roundup", NOW - timedelta(days=1))
    npu = item(db_session, good, "Qualcomm NPU roadmap leaks")
    skipped = item(db_session, bad, "AI agent news from a paused feed")

    assert (
        embed_titles(db_session, fake_embed, model="m", now=NOW, limit=100) == 3
    )  # paused skipped
    assert score_pending(db_session, now=NOW, limit=100) == 3
    scores = {t.item_id: t for t in db_session.scalars(select(ItemTriage))}
    assert scores[dx.id].dx_probability > 0.8 > 0.2 > scores[junk.id].dx_probability
    order = [i.id for i, _ in pending_items(db_session, limit=10)]
    assert order.index(dx.id) < order.index(junk.id) and skipped.id not in order

    apply(
        db_session,
        ChangeSet.model_validate(
            {"ops": [{"op": "update_node", "scheme": "technology", "key": "semis", "priority": 0}]}
        ),
        author="t",
        now=NOW,
    )
    assert (
        db_session.scalar(select(ItemTriage.model_id).where(ItemTriage.item_id == npu.id)) is None
    )
    score_pending(db_session, now=NOW, limit=100)
    weight = db_session.scalar(select(ItemTriage.weight).where(ItemTriage.item_id == npu.id))
    assert weight == 0.0 and npu.id not in [i.id for i, _ in pending_items(db_session, limit=10)]


def test_named_technologies_and_the_newest_share(db_session: Session, model: int) -> None:
    src = source(db_session, "good")
    apply(
        db_session,
        ChangeSet.model_validate(
            {"ops": [{"op": "update_node", "scheme": "technology", "key": "llm", "priority": 2}]}
        ),
        author="t",
        now=NOW,
    )
    named = item(db_session, src, "Cheap LLM serving trick", NOW - timedelta(days=2))
    for n in range(12):
        item(db_session, src, f"AI agent update {n}", NOW - timedelta(hours=n + 1))
    embed_titles(db_session, fake_embed, model="m", now=NOW, limit=100)
    score_pending(db_session, now=NOW, limit=100)
    row = db_session.scalars(select(ItemTriage).where(ItemTriage.item_id == named.id)).one()
    assert row.weight == 2.0 and row.matched == ["technology:llm"]
    picked = pending_items(db_session, limit=10)
    assert picked[0][0].id == named.id and len(picked) == 10
    assert "llm" in title_keys("Cheap LLM serving") and "llmserving" in title_keys(
        "Cheap LLM serving"
    )
