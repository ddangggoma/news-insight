from datetime import UTC, datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.stories.models import ItemEmbedding
from news_insight.taxonomy import embeddings
from news_insight.taxonomy.embeddings import clusters, misfits, similar
from news_insight.taxonomy.seed import seed_taxonomy
from tests.taxonomy.test_schemes import node
from tests.technologies.test_registry import card_for


def unit(*hot: int) -> list[float]:
    vector = np.zeros(1024, dtype=np.float32)
    for index in hot:
        vector[index] = 1.0
    return [float(v) for v in vector / np.linalg.norm(vector)]


def fake_embed(table: dict[str, list[float]]):
    return lambda texts: [table[t] for t in texts]


def test_clusters_group_phrases_by_meaning() -> None:
    table = {
        "위성 직접통신": unit(1),
        "위성 D2D": unit(1, 2),
        "액체냉각": unit(5),
        "D2D 위성": unit(1),
    }
    rows = [
        {"key": "a", "label": "위성 D2D", "count": 3},
        {"key": "b", "label": "위성 직접통신", "count": 9},
        {"key": "c", "label": "액체냉각", "count": 4},
        {"key": "d", "label": "D2D 위성", "count": 1},
    ]
    got = clusters(rows, embed=fake_embed(table), threshold=0.7)
    assert [(c.label, c.count, len(c.phrases)) for c in got] == [
        ("위성 직접통신", 13, 3),
        ("액체냉각", 4, 1),
    ]


@pytest.mark.db
def test_similar_and_misfits_use_the_pgvector_copy(db_session: Session) -> None:
    seed_taxonomy(db_session)
    agents = node(db_session, "technology", "ai__ai_agents")
    cards = [card_for(db_session, []) for _ in range(4)]
    vectors = [unit(1), unit(1, 2), unit(1, 3), unit(9)]
    for card, vector in zip(cards, vectors, strict=True):
        db_session.add(
            ItemEmbedding(
                item_id=card.item_id, model="m", vector=vector, created_at=datetime.now(UTC)
            )
        )
    db_session.flush()
    assert (
        db_session.scalar(
            select(ItemEmbedding.embedding).where(ItemEmbedding.item_id == cards[0].item_id)
        )
        is not None
    )
    for card in cards[:3] + cards[3:]:
        db_session.execute(
            update(ItemCard)
            .where(ItemCard.id == card.id)
            .values(themes=["ai__ai_agents"], field="ai")
        )

    found = similar(
        db_session, "에이전트", node_id=agents.id, limit=3, embed=fake_embed({"에이전트": unit(1)})
    )
    odd = misfits(db_session, agents.id, limit=2)

    assert found.cards[0].item_id == cards[0].item_id and found.cards[
        0
    ].similarity == pytest.approx(1.0)
    assert all(c.labelled for c in found.cards) and found.unlabelled == 0
    assert odd.members == 4 and odd.cards[0].item_id == cards[3].item_id


@pytest.mark.db
def test_routes_answer_503_without_the_embedding_model(
    console_client: TestClient,
    headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_taxonomy(db_session)

    def down():
        def embed(texts: list[str]) -> list[list[float]]:
            raise embeddings.EmbeddingUnavailable("embedding model unavailable: refused")

        return embed

    monkeypatch.setattr(embeddings, "embedder", down)
    response = console_client.post(
        "/api/admin/taxonomy/similar", json={"text": "AI"}, headers=headers
    )
    agents = node(db_session, "technology", "ai__ai_agents")
    empty = console_client.get(
        f"/api/admin/taxonomy/nodes/{agents.id}/misfits", headers=headers
    ).json()

    assert response.status_code == 503 and "unavailable" in response.text
    assert empty == {"members": 0, "mean_similarity": None, "cards": []}
