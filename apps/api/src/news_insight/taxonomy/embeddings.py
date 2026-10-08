"""Embedding help for the taxonomy workspace (plan 15-6), on the pgvector copy of the bge-m3
title embeddings (`item_embeddings.embedding`).

- similar: cards whose titles read like a text (a node's name and definition), and whether
  each already sits under the node — what a new or redefined node would gather;
- misfits: cards under a node farthest from the node's centre — likely misclassified;
- clusters: unclassified-topic phrases grouped by meaning, so ten spellings become one row.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

Embed = Callable[[list[str]], list[list[float]]]
CLUSTER_SIMILARITY = 0.8


class EmbeddingUnavailable(RuntimeError):
    """LM Studio did not answer (the embedding model runs on the host)."""


def embedder() -> Embed:
    from news_insight.config import get_settings
    from news_insight.stories.semantic import lm_studio_embed

    settings = get_settings()
    inner = lm_studio_embed(settings.lm_studio_url, settings.lm_studio_embedding_model, timeout=60)

    def embed(texts: list[str]) -> list[list[float]]:
        try:
            return inner(texts)
        except Exception as exc:  # noqa: BLE001 - httpx errors, a missing model, bad JSON
            raise EmbeddingUnavailable(f"embedding model unavailable: {exc}") from exc

    return embed


def _literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


class SimilarCard(BaseModel):
    item_id: int
    title: str | None
    similarity: float
    first_seen_at: datetime
    labelled: bool  # already under the node (or a node below it)


class SimilarResult(BaseModel):
    query: str
    cards: list[SimilarCard]
    unlabelled: int


def similar(
    session: Session, query: str, *, node_id: int | None, limit: int, embed: Embed
) -> SimilarResult:
    vector = embed([query])[0]
    rows = session.execute(
        text(
            "SELECT e.item_id, coalesce(c.title_ko, i.title),"
            " 1 - (e.embedding <=> CAST(:q AS vector)), i.first_seen_at,"
            " EXISTS (SELECT 1 FROM card_labels l JOIN tax_nodes n ON n.id = l.node_id"
            "         WHERE l.item_id = e.item_id AND :node = ANY(n.path))"
            " FROM item_embeddings e JOIN items i ON i.id = e.item_id"
            " LEFT JOIN item_cards c ON c.item_id = e.item_id"
            " WHERE e.embedding IS NOT NULL"
            " ORDER BY e.embedding <=> CAST(:q AS vector) LIMIT :n"
        ),
        {"q": _literal(vector), "node": node_id or 0, "n": limit},
    ).all()
    cards = [
        SimilarCard(
            item_id=r[0],
            title=r[1],
            similarity=round(float(r[2]), 3),
            first_seen_at=r[3],
            labelled=bool(r[4]),
        )
        for r in rows
    ]
    return SimilarResult(query=query, cards=cards, unlabelled=sum(not c.labelled for c in cards))


class Misfit(BaseModel):
    item_id: int
    title: str | None
    similarity: float  # to the centre of the node's cards


class MisfitResult(BaseModel):
    members: int
    mean_similarity: float | None
    cards: list[Misfit]


def misfits(session: Session, node_id: int, *, limit: int, sample: int = 3000) -> MisfitResult:
    """The node's least typical cards among its most recent `sample`."""
    rows = session.execute(
        text(
            "WITH members AS ("
            "  SELECT DISTINCT ON (l.item_id) l.item_id, e.embedding FROM card_labels l"
            "  JOIN tax_nodes n ON n.id = l.node_id"
            "  JOIN item_embeddings e ON e.item_id = l.item_id AND e.embedding IS NOT NULL"
            "  WHERE :node = ANY(n.path) ORDER BY l.item_id DESC LIMIT :sample"
            "), centre AS (SELECT avg(embedding) AS c FROM members)"
            " SELECT m.item_id, coalesce(c.title_ko, i.title),"
            " 1 - (m.embedding <=> (SELECT c FROM centre)) AS sim,"
            " count(*) OVER (), avg(1 - (m.embedding <=> (SELECT c FROM centre))) OVER ()"
            " FROM members m JOIN items i ON i.id = m.item_id"
            " LEFT JOIN item_cards c ON c.item_id = m.item_id"
            " ORDER BY sim ASC LIMIT :n"
        ),
        {"node": node_id, "n": limit, "sample": sample},
    ).all()
    if not rows:
        return MisfitResult(members=0, mean_similarity=None, cards=[])
    return MisfitResult(
        members=int(rows[0][3]),
        mean_similarity=round(float(rows[0][4]), 3),
        cards=[Misfit(item_id=r[0], title=r[1], similarity=round(float(r[2]), 3)) for r in rows],
    )


class Cluster(BaseModel):
    label: str  # the most reported phrase
    count: int  # reports across the phrases
    phrases: list[dict[str, Any]]  # {key, label, count}


def clusters(
    candidates: list[dict[str, Any]], *, embed: Embed, threshold: float = CLUSTER_SIMILARITY
) -> list[Cluster]:
    """Greedy grouping, most reported first: a phrase joins the first group whose leader it
    resembles (cosine >= threshold), otherwise leads a new one."""
    ordered = sorted(candidates, key=lambda c: -int(c["count"]))
    if not ordered:
        return []
    vectors = np.asarray(embed([str(c["label"]) for c in ordered]), dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
    leaders: list[int] = []
    groups: list[list[int]] = []
    for index in range(len(ordered)):
        if leaders:
            scores = vectors[leaders] @ vectors[index]
            best = int(np.argmax(scores))
            if scores[best] >= threshold:
                groups[best].append(index)
                continue
        leaders.append(index)
        groups.append([index])
    out = [
        Cluster(
            label=str(ordered[g[0]]["label"]),
            count=sum(int(ordered[i]["count"]) for i in g),
            phrases=[
                {
                    "key": ordered[i]["key"],
                    "label": ordered[i]["label"],
                    "count": ordered[i]["count"],
                }
                for i in g
            ],
        )
        for g in groups
    ]
    out.sort(key=lambda c: -c.count)
    return out
