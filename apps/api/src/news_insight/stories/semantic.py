"""Multilingual story merging (checklist CLU-1).

MinHash on card titles misses the same event told in other words or another language ("LeCun has
zero concerns…" and "LeCun, AI의 인류 멸종…"). Each clustered item's original title is embedded
with a multilingual model (bge-m3 in LM Studio); its nearest neighbour from another story and
another publisher in the last WINDOW becomes a candidate when the cosine clears COSINE and the
titles do not carry different identifiers. Embedding similarity alone is not precise enough
(about 70 % same-event at 0.78 on 2026-10-05: templated feeds such as CVE bulletins and phishing
alerts look alike), so an LLM judge confirms every candidate before two stories are merged.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.content.models import Item
from news_insight.sources.models import Source
from news_insight.stories.evaluate import Ask, Pair, judge
from news_insight.stories.models import (
    ItemEmbedding,
    Relation,
    Story,
    StoryItem,
    StoryMergeCheck,
)
from news_insight.stories.service import WINDOW

COSINE = 0.75
MIN_WORDS = 4
JUDGE_BATCH = 50
CHUNK = 512  # rows per matrix product when scoring neighbours
INSERT_ROWS = 256  # embeddings per INSERT (PostgreSQL allows 65,535 bind parameters)
Embed = Callable[[list[str]], list[list[float]]]

URL = re.compile(r"https?://\S+")
DEFANGED = re.compile(r"\[(\.|:)\]")
DOMAIN = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)+\b")
IDENT = re.compile(r"[\w./-]*\d[\w./-]*")
CJK = re.compile(r"[぀-ヿ㐀-鿿가-힣]")


def identifiers(title: str) -> set[str]:
    """Version numbers, ids, years and (defanged) domains: two titles that each carry one the other
    lacks are different bulletins of one template (CVE-…-1 vs CVE-…-2, two phishing domains)."""
    text = URL.sub(" ", title)
    text = DEFANGED.sub(lambda m: m.group(1), text).lower()
    found = set(DOMAIN.findall(text.replace("hxxps://", " ").replace("hxxp://", " ")))
    for token in IDENT.findall(text):
        token = token.strip("./-")
        if len(token) >= 4 or any(c in token for c in "./-"):
            found.add(token)
    return found


def words(title: str) -> int:
    """Word count, with CJK text counted as one word per two characters."""
    text = URL.sub(" ", title)
    cjk = len(CJK.findall(text))
    return len(re.findall(r"[A-Za-z0-9]+", text)) + cjk // 2


def plausible(a: str, b: str) -> bool:
    ia, ib = identifiers(a), identifiers(b)
    if ia - ib and ib - ia:
        return False
    return min(words(a), words(b)) >= MIN_WORDS


@dataclass
class SemanticStats:
    embedded: int = 0
    candidates: int = 0
    judged: int = 0
    merged: int = 0
    skipped: dict[str, int] = field(default_factory=dict)


def embed_pending(
    session: Session, embed: Embed, *, model: str, now: datetime, limit: int = 500
) -> int:
    """Embed clustered items of the last WINDOW that have no vector yet."""
    rows = list(
        session.execute(
            select(Item.id, Item.title, ItemCard.title_ko)
            .join(StoryItem, StoryItem.item_id == Item.id)
            .join(ItemCard, ItemCard.item_id == Item.id)
            .outerjoin(ItemEmbedding, ItemEmbedding.item_id == Item.id)
            .where(ItemEmbedding.item_id.is_(None), Item.first_seen_at >= now - WINDOW)
            .order_by(Item.first_seen_at.desc())
            .limit(limit)
        ).tuples()
    )
    if not rows:
        return 0
    for start in range(0, len(rows), INSERT_ROWS):
        chunk = rows[start : start + INSERT_ROWS]
        vectors = embed([(title or title_ko or "")[:500] for _, title, title_ko in chunk])
        session.execute(
            insert(ItemEmbedding)
            .values(
                [
                    {"item_id": item_id, "model": model, "vector": vector, "created_at": now}
                    for (item_id, _, _), vector in zip(chunk, vectors, strict=True)
                ]
            )
            .on_conflict_do_nothing()
        )
        session.flush()
    return len(rows)


@dataclass(frozen=True)
class Candidate:
    item_a: int
    item_b: int
    title_a: str
    title_b: str
    cosine: float


def candidates(
    session: Session, *, model: str, now: datetime, since: datetime | None = None
) -> tuple[list[Candidate], dict[str, int]]:
    """Each recently embedded item's nearest neighbour from another story and publisher."""
    rows = list(
        session.execute(
            select(
                Item.id,
                Item.title,
                StoryItem.story_id,
                Source.official_domain,
                ItemEmbedding.vector,
                ItemEmbedding.created_at,
            )
            .join(ItemEmbedding, ItemEmbedding.item_id == Item.id)
            .join(StoryItem, StoryItem.item_id == Item.id)
            .join(Source, Source.id == Item.source_id)
            .where(ItemEmbedding.model == model, Item.first_seen_at >= now - WINDOW)
        ).tuples()
    )
    skipped: dict[str, int] = {}
    if len(rows) < 2:
        return [], skipped
    matrix = np.asarray([row[4] for row in rows], dtype=np.float32)
    matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-9)
    stories = np.asarray([row[2] for row in rows])
    domains = [row[3] for row in rows]
    checked = {
        (a, b)
        for a, b in session.execute(select(StoryMergeCheck.item_a, StoryMergeCheck.item_b)).tuples()
    }
    fresh = [i for i, row in enumerate(rows) if since is None or row[5] >= since]
    found: dict[tuple[int, int], Candidate] = {}
    for start in range(0, len(fresh), CHUNK):
        block = fresh[start : start + CHUNK]
        block_scores = matrix[block] @ matrix.T
        for row_scores, i in zip(block_scores, block, strict=True):
            _nearest(row_scores, i, rows, stories, domains, checked, found, skipped)
    return list(found.values()), skipped


def _nearest(
    scores: Any,
    i: int,
    rows: list[Any],
    stories: Any,
    domains: list[str],
    checked: set[tuple[int, int]],
    found: dict[tuple[int, int], Candidate],
    skipped: dict[str, int],
) -> None:
    """Record item i's best neighbour from another story and publisher, if it qualifies."""
    scores[stories == stories[i]] = -1.0  # same story (and the item itself)
    for j in np.argsort(-scores)[:5]:
        cosine = float(scores[j])
        if cosine < COSINE:
            break
        if domains[j] == domains[i]:
            continue
        a, b = sorted((rows[i][0], rows[int(j)][0]))
        if (a, b) in checked or (a, b) in found:
            break
        ta, tb = rows[i][1], rows[int(j)][1]
        if not plausible(ta, tb):
            skipped["guard"] = skipped.get("guard", 0) + 1
            break
        first, second = (ta, tb) if rows[i][0] == a else (tb, ta)
        found[(a, b)] = Candidate(a, b, first, second, round(cosine, 4))
        break


def _refresh(session: Session, story: Story) -> None:
    """Recount a story's aggregates from its members."""
    members = list(
        session.execute(
            select(Item, Source.official_domain, ItemCard.relevance, ItemCard.title_ko)
            .join(StoryItem, StoryItem.item_id == Item.id)
            .join(Source, Source.id == Item.source_id)
            .outerjoin(ItemCard, ItemCard.item_id == Item.id)
            .where(StoryItem.story_id == story.id)
        ).tuples()
    )
    story.item_count = len(members)
    story.source_count = len({domain for _, domain, _, _ in members}) or 1
    story.first_seen_at = min(item.first_seen_at for item, _, _, _ in members)
    story.last_seen_at = max(item.first_seen_at for item, _, _, _ in members)
    story.tracks = sorted({item.track.value for item, _, _, _ in members})
    lead = max(members, key=lambda m: (m[2] or -1, -m[0].id))
    story.representative_item_id = lead[0].id
    story.title_ko = lead[3]
    story.max_relevance = lead[2]


def merge(session: Session, item_a: int, item_b: int, cosine: float, now: datetime) -> bool:
    """Fold the smaller of the two items' stories into the larger one."""
    story_ids = dict(
        session.execute(
            select(StoryItem.item_id, StoryItem.story_id).where(
                StoryItem.item_id.in_([item_a, item_b])
            )
        )
        .tuples()
        .all()
    )
    if len(story_ids) < 2 or story_ids[item_a] == story_ids[item_b]:
        return False
    first, second = session.get(Story, story_ids[item_a]), session.get(Story, story_ids[item_b])
    assert first is not None and second is not None
    keep, fold = (first, second) if first.item_count >= second.item_count else (second, first)
    bridge = item_b if fold is second else item_a
    session.execute(update(StoryItem).where(StoryItem.story_id == fold.id).values(story_id=keep.id))
    session.execute(
        update(StoryItem)
        .where(StoryItem.item_id == bridge)
        .values(relation=Relation.SEMANTIC, similarity=cosine, joined_at=now)
    )
    session.flush()
    session.execute(delete(Story).where(Story.id == fold.id))
    _refresh(session, keep)
    session.flush()
    return True


def run(
    session: Session,
    *,
    embed: Embed,
    ask: Ask,
    model: str,
    now: datetime,
    since: datetime | None = None,
    max_judged: int = 200,
    embed_limit: int = 500,
) -> SemanticStats:
    """Embed, find candidates, judge them, merge the confirmed ones."""
    stats = SemanticStats()
    stats.embedded = embed_pending(session, embed, model=model, now=now, limit=embed_limit)
    found, stats.skipped = candidates(session, model=model, now=now, since=since)
    found = sorted(found, key=lambda c: -c.cosine)[:max_judged]
    stats.candidates = len(found)
    if not found:
        return stats
    pairs = [Pair(id=n, a=c.title_a, b=c.title_b, score=c.cosine) for n, c in enumerate(found)]
    labels = judge(ask, pairs, batch=JUDGE_BATCH)
    stats.judged = len(labels)
    for n, candidate in enumerate(found):
        same = labels.get(n)
        session.execute(
            insert(StoryMergeCheck)
            .values(
                item_a=candidate.item_a,
                item_b=candidate.item_b,
                cosine=candidate.cosine,
                same=same,
                checked_at=now,
            )
            .on_conflict_do_nothing()
        )
        if same and merge(session, candidate.item_a, candidate.item_b, candidate.cosine, now):
            stats.merged += 1
    session.flush()
    return stats


def lm_studio_embed(base_url: str, model: str, *, timeout: float = 600) -> Embed:
    """Embeddings from LM Studio's OpenAI-compatible endpoint, 64 titles per request."""
    import httpx

    def embed(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=timeout) as client:
            for start in range(0, len(texts), 64):
                response = client.post(
                    f"{base_url.rstrip('/')}/v1/embeddings",
                    json={"model": model, "input": texts[start : start + 64]},
                )
                response.raise_for_status()
                data: Sequence[dict[str, Any]] = response.json()["data"]
                vectors.extend(
                    entry["embedding"] for entry in sorted(data, key=lambda d: d["index"])
                )
        return vectors

    return embed
