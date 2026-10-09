"""Carding priority before the LLM (plan 16 #3).

Items arrive at 17-30k a day and the engines card 4-11k, so what is carded first decides what
the briefing and the radar can see. Newest-first spent 35-40% of the cards on items the LLM then
marked irrelevant. Measured on the live cards (2026-10-09, newest 30% held out):

- a ridge model on the bge-m3 title embedding separates DX from the rest at AUC 0.85
  (the source's own DX history alone: 0.68; both: 0.86);
- with capacity for 40% of the inflow, carding by this score captures 56% of the DX items
  instead of 40%, and 90% of the cards are DX instead of 64%.

Every item first gets a title embedding (the same text and model the story merger uses, so it
reuses them), then a score: DX probability × the node priority the reader set (themes and fields
through the nearest theme centroids, technologies and companies when their names appear in the
title) + a boost for watch-list subjects. Excluded nodes (priority 0) are never carded.
"""

import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard, ItemTriage, TriageModel
from news_insight.content.models import Item
from news_insight.sources.enums import SourceStatus
from news_insight.sources.models import Source
from news_insight.stories.models import ItemEmbedding
from news_insight.technologies.catalog import normalize

Embed = Callable[[list[str]], list[list[float]]]
TRAIN_WINDOW = timedelta(days=60)
TRAIN_SAMPLE = 20000
RIDGE = 3.0
PRIOR_STRENGTH = 5.0
PRIOR_WEIGHT = 0.5  # the source history next to the title score (measured best at ~0.5)
WATCH_BOOST = 0.25
MATCH_FLOOR = 0.6  # a title naming a technology or company the reader weighted is likely DX
FRESH_BOOST = 0.05  # first seen in the last 6 hours
FRESH = timedelta(hours=6)
PRIORITIES = (0.0, 0.5, 1.0, 1.5, 2.0)  # 제외, 낮음, 보통, 높음, 최우선
MAX_NGRAM = 3
WORD = re.compile(r"[\w가-힣][\w가-힣.+\-]*", re.UNICODE)


MIN_SPREAD = 0.05
CLIP = 3.0  # standardised terms beyond ±3 spreads carry no extra information


def _combine(linear: Any, prior: Any, stats: dict[str, float]) -> Any:
    title = np.clip((linear - stats["linear_mean"]) / stats["linear_std"], -CLIP, CLIP)
    source = np.clip((prior - stats["prior_mean"]) / stats["prior_std"], -CLIP, CLIP)
    return title + PRIOR_WEIGHT * source


def _vectors(rows: Iterable[Any]) -> np.ndarray:
    matrix = np.asarray([list(r) for r in rows], dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    return matrix


def _auc(score: np.ndarray, label: np.ndarray) -> float:
    order = np.argsort(score)
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    pos = label == 1
    n1, n0 = int(pos.sum()), int((~pos).sum())
    if not n1 or not n0:
        return 0.5
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _platt(score: np.ndarray, label: np.ndarray) -> tuple[float, float]:
    """Logistic calibration p = 1 / (1 + exp(-(a·s + b))) by Newton's method."""
    a, b = 1.0, 0.0
    for _ in range(25):
        p = 1 / (1 + np.exp(-(a * score + b)))
        g = np.array([((p - label) * score).sum(), (p - label).sum()])
        w = p * (1 - p)
        h = np.array([[(w * score * score).sum(), (w * score).sum()], [(w * score).sum(), w.sum()]])
        step = np.linalg.solve(h + 1e-6 * np.eye(2), g)
        a, b = a - step[0], b - step[1]
        if abs(step).max() < 1e-6:
            break
    return float(a), float(b)


def source_priors(session: Session, *, now: datetime) -> tuple[dict[int, float], float]:
    rows = (
        session.execute(
            select(
                Item.source_id,
                func.count(),
                func.count().filter(ItemCard.scope.in_(("dx", "dx_dependency"))),
            )
            .join(ItemCard, ItemCard.item_id == Item.id)
            .where(
                ItemCard.status == CardStatus.READY,
                ItemCard.generated_at >= now - timedelta(days=30),
            )
            .group_by(Item.source_id)
        )
        .tuples()
        .all()
    )
    total = sum(int(n) for _, n, _ in rows)
    base = sum(int(d) for _, _, d in rows) / total if total else 0.6
    return {
        int(sid): (int(d) + PRIOR_STRENGTH * base) / (int(n) + PRIOR_STRENGTH) for sid, n, d in rows
    }, base


@dataclass(frozen=True)
class TrainResult:
    model_id: int
    samples: int
    auc: float


def train(session: Session, *, now: datetime, sample: int = TRAIN_SAMPLE) -> TrainResult | None:
    """Fit on recent cards with embeddings (oldest 70% train, newest 30% measure); store active."""
    rows = (
        session.execute(
            select(
                ItemEmbedding.vector,
                ItemCard.scope.in_(("dx", "dx_dependency")),
                Item.source_id,
                ItemCard.generated_at,
                ItemCard.themes,
            )
            .join(ItemCard, ItemCard.item_id == ItemEmbedding.item_id)
            .join(Item, Item.id == ItemEmbedding.item_id)
            .where(
                ItemCard.status == CardStatus.READY,
                ItemCard.scope.is_not(None),
                ItemCard.generated_at >= now - TRAIN_WINDOW,
                func.array_length(ItemEmbedding.vector, 1) == 1024,
            )
            .order_by(func.random())
            .limit(sample)
        )
        .tuples()
        .all()
    )
    if len(rows) < 500:
        return None
    x = _vectors(r[0] for r in rows)
    y = np.asarray([1.0 if r[1] else 0.0 for r in rows], dtype=np.float32)
    sources = np.asarray([int(r[2]) for r in rows])
    times = np.asarray([r[3].timestamp() for r in rows])
    train_mask = times < np.quantile(times, 0.7)
    test_mask = ~train_mask
    xb = np.hstack([x, np.ones((len(x), 1), dtype=np.float32)])
    a = xb[train_mask]
    weights = np.linalg.solve(
        a.T @ a + RIDGE * np.eye(a.shape[1], dtype=np.float32), a.T @ (2 * y[train_mask] - 1)
    )
    linear = xb @ weights
    priors, base = source_priors(session, now=now)
    prior = np.asarray([priors.get(int(s), base) for s in sources], dtype=np.float32)
    stats = {
        "linear_mean": float(linear[train_mask].mean()),
        "linear_std": max(float(linear[train_mask].std()), MIN_SPREAD),
        "prior_mean": float(prior[train_mask].mean()),
        # one source in the sample gives no spread: a floor keeps a new source's prior sane
        "prior_std": max(float(prior[train_mask].std()), MIN_SPREAD),
        "base_rate": float(base),
    }
    combined = _combine(linear, prior, stats)
    stats["platt_a"], stats["platt_b"] = _platt(combined[test_mask], y[test_mask])
    auc = _auc(combined[test_mask], y[test_mask])
    centroids: dict[str, np.ndarray] = {}
    counts: dict[str, int] = {}
    for vector, (_, _, _, _, themes) in zip(x, rows, strict=True):
        for theme in themes or []:
            centroids[theme] = centroids.get(theme, np.zeros(1024, dtype=np.float32)) + vector
            counts[theme] = counts.get(theme, 0) + 1
    unit = {
        k: (v / (np.linalg.norm(v) + 1e-9)).round(5).tolist()
        for k, v in centroids.items()
        if counts[k] >= 5
    }
    session.execute(text("UPDATE triage_models SET active = false WHERE active"))
    model = TriageModel(
        trained_at=now,
        samples=len(rows),
        auc=round(auc, 4),
        weights=weights.round(6).tolist(),
        centroids=unit,
        stats=stats,
        active=True,
    )
    session.add(model)
    session.flush()
    return TrainResult(model_id=model.id, samples=len(rows), auc=round(auc, 4))


def active_model(session: Session) -> TriageModel | None:
    return session.scalars(
        select(TriageModel).where(TriageModel.active).order_by(TriageModel.id.desc()).limit(1)
    ).first()


def title_keys(title: str) -> set[str]:
    """Normalised word n-grams (up to three words): how registry keys and aliases are written."""
    words = WORD.findall(title.lower())
    keys: set[str] = set()
    for size in range(1, MAX_NGRAM + 1):
        for start in range(len(words) - size + 1):
            key = normalize(" ".join(words[start : start + size]))
            if len(key) >= 2:
                keys.add(key)
    return keys


@dataclass(frozen=True)
class Weights:
    """Node priorities the reader set (tax_nodes.attrs.priority), and what they apply to."""

    themes: dict[str, float]  # theme or field key -> priority (technology scheme, LLM depth)
    by_match_key: dict[str, tuple[str, float]]  # normalised key/alias -> (scheme:key, priority)
    fields: dict[str, str]  # theme key -> its field key

    def weight(self, predicted: list[str], matched: list[tuple[str, float]]) -> float:
        explicit = [p for _, p in matched]
        if explicit:  # a named technology or company decides; the strongest signal wins
            return 0.0 if min(explicit) == 0.0 and max(explicit) <= 1.0 else max(explicit)
        if predicted:
            top = predicted[0]
            if top in self.themes:
                return self.themes[top]
            field = self.fields.get(top)
            if field in self.themes:
                return self.themes[field]
        return 1.0


def node_weights(session: Session) -> Weights:
    rows = (
        session.execute(
            text(
                "SELECT s.key, n.key, n.depth, coalesce(s.llm_depth, 0), n.attrs ->> 'priority',"
                " p.key, n.aliases"
                " FROM tax_nodes n JOIN tax_schemes s ON s.id = n.scheme_id"
                " LEFT JOIN tax_nodes p ON p.id = n.parent_id"
                " WHERE n.status = 'active' AND s.key = 'technology'"
            )
        )
        .tuples()
        .all()
    )
    themes: dict[str, float] = {}
    by_key: dict[str, tuple[str, float]] = {}
    fields: dict[str, str] = {}
    for scheme, key, depth, llm_depth, priority, parent, aliases in rows:
        if depth == 2 and parent:
            fields[key] = parent
        if priority is None:
            continue
        value = float(priority)
        if depth <= llm_depth:
            themes[key] = value
        else:
            for alias in [key, *(aliases or [])]:
                by_key[normalize(alias)] = (f"{scheme}:{key}", value)
    return Weights(themes=themes, by_match_key=by_key, fields=fields)


def watch_keys(session: Session) -> tuple[set[str], set[str]]:
    """(normalised names in titles, themes) the watch list follows."""
    names: set[str] = set()
    themes: set[str] = set()
    for kind, key in session.execute(text("SELECT kind, key FROM watch_items")).tuples():
        if kind == "keyword":
            names.add(normalize(key))
        elif kind == "theme":
            themes.add(key)
        elif kind == "company":
            names.update(
                normalize(a)
                for (a,) in session.execute(
                    text("SELECT alias FROM company_aliases WHERE company_key = :k"), {"k": key}
                )
            )
            names.add(normalize(key))
        elif kind == "node" and key.startswith("technology:"):
            themes.add(key.split(":", 1)[1])
    return names, themes


def embed_titles(session: Session, embed: Embed, *, model: str, now: datetime, limit: int) -> int:
    """Title embeddings for fresh items that have neither a card nor a vector yet."""
    rows = (
        session.execute(
            select(Item.id, Item.title)
            .join(Source, Source.id == Item.source_id)
            .outerjoin(ItemCard, ItemCard.item_id == Item.id)
            .outerjoin(ItemEmbedding, ItemEmbedding.item_id == Item.id)
            .where(
                ItemCard.id.is_(None),
                ItemEmbedding.item_id.is_(None),
                Source.status.not_in((SourceStatus.PAUSED, SourceStatus.RETIRED)),
                Item.first_seen_at >= now - timedelta(days=14),
            )
            .order_by(Item.first_seen_at.desc())
            .limit(limit)
        )
        .tuples()
        .all()
    )
    for start in range(0, len(rows), 64):
        chunk = rows[start : start + 64]
        vectors = embed([(title or "")[:500] for _, title in chunk])
        session.execute(
            insert(ItemEmbedding)
            .values(
                [
                    {"item_id": item_id, "model": model, "vector": vector, "created_at": now}
                    for (item_id, _), vector in zip(chunk, vectors, strict=True)
                ]
            )
            .on_conflict_do_nothing()
        )
        session.flush()
    return len(rows)


def score_pending(session: Session, *, now: datetime, limit: int) -> int:
    """Score embedded, uncarded items not yet scored by the active model."""
    model = active_model(session)
    if model is None:
        return 0
    rows = (
        session.execute(
            select(Item.id, Item.title, Item.source_id, Item.first_seen_at, ItemEmbedding.vector)
            .join(ItemEmbedding, ItemEmbedding.item_id == Item.id)
            .outerjoin(ItemCard, ItemCard.item_id == Item.id)
            .outerjoin(ItemTriage, ItemTriage.item_id == Item.id)
            .where(
                ItemCard.id.is_(None),
                func.array_length(ItemEmbedding.vector, 1) == 1024,
                (ItemTriage.item_id.is_(None)) | (ItemTriage.model_id.is_distinct_from(model.id)),
                Item.first_seen_at >= now - timedelta(days=14),
            )
            .order_by(Item.first_seen_at.desc())
            .limit(limit)
        )
        .tuples()
        .all()
    )
    if not rows:
        return 0
    stats = model.stats
    weights = np.asarray(model.weights, dtype=np.float32)
    keys = list(model.centroids)
    centroids = np.asarray([model.centroids[k] for k in keys], dtype=np.float32) if keys else None
    priors, base = source_priors(session, now=now)
    node = node_weights(session)
    watch_names, watch_themes = watch_keys(session)
    x = _vectors(r[4] for r in rows)
    linear = np.hstack([x, np.ones((len(x), 1), dtype=np.float32)]) @ weights
    values = []
    for index, (item_id, title, source_id, seen, _) in enumerate(rows):
        prior = priors.get(int(source_id), base)
        combined = (float(linear[index]) - stats["linear_mean"]) / stats[
            "linear_std"
        ] + PRIOR_WEIGHT * (prior - stats["prior_mean"]) / stats["prior_std"]
        probability = 1 / (1 + math.exp(-(stats["platt_a"] * combined + stats["platt_b"])))
        predicted = (
            [keys[j] for j in np.argsort(-(centroids @ x[index]))[:3]]
            if centroids is not None
            else []
        )
        tkeys = title_keys(title or "")
        matched = [node.by_match_key[k] for k in tkeys if k in node.by_match_key]
        weight = node.weight(predicted, matched)
        boost = 0.0
        if weight > 0 and (
            (tkeys & watch_names) or (predicted[:1] and predicted[0] in watch_themes)
        ):
            boost += WATCH_BOOST
        if weight > 0 and now - seen <= FRESH:
            boost += FRESH_BOOST
        values.append(
            {
                "item_id": item_id,
                "model_id": model.id,
                "dx_probability": round(probability, 4),
                "weight": weight,
                "score": round(
                    (max(probability, MATCH_FLOOR) if matched else probability) * weight + boost, 4
                ),
                "themes": predicted,
                "matched": sorted({ref for ref, _ in matched}),
                "scored_at": now,
            }
        )
    statement = insert(ItemTriage).values(values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[ItemTriage.item_id],
            set_={
                c: statement.excluded[c]
                for c in (
                    "model_id",
                    "dx_probability",
                    "weight",
                    "score",
                    "themes",
                    "matched",
                    "scored_at",
                )
            },
        )
    )
    session.flush()
    return len(values)


def rescore_all(session: Session, *, now: datetime) -> int:
    """After a node priority change: score every uncarded item again (cheap, no embedding)."""
    session.execute(text("UPDATE item_triage SET model_id = NULL"))
    total = 0
    while True:
        done = score_pending(session, now=now, limit=5000)
        total += done
        if done < 5000:
            return total


@dataclass(frozen=True)
class Coverage:
    model_id: int | None
    trained_at: datetime | None
    auc: float | None
    samples: int
    scored_waiting: int  # scored items without a card
    top_carded_24h: float | None  # share of the top 30% (by score) seen 24-48 h ago now carded
    dx_share_24h: float | None  # DX share of the cards written in the last 24 hours


def coverage(session: Session, *, now: datetime) -> Coverage:
    model = active_model(session)
    waiting = session.scalar(
        select(func.count())
        .select_from(ItemTriage)
        .outerjoin(ItemCard, ItemCard.item_id == ItemTriage.item_id)
        .where(ItemCard.id.is_(None))
    )
    window = session.execute(
        text(
            "WITH w AS (SELECT t.item_id, t.score, c.id AS card FROM item_triage t"
            " JOIN items i ON i.id = t.item_id LEFT JOIN item_cards c ON c.item_id = t.item_id"
            " WHERE i.first_seen_at BETWEEN :a AND :b),"
            " q AS (SELECT percentile_cont(0.7) WITHIN GROUP (ORDER BY score) AS cut FROM w)"
            " SELECT count(*) FILTER (WHERE card IS NOT NULL), count(*)"
            " FROM w, q WHERE score >= q.cut"
        ),
        {"a": now - timedelta(hours=48), "b": now - timedelta(hours=24)},
    ).one()
    share = session.execute(
        select(
            func.count().filter(ItemCard.scope.in_(("dx", "dx_dependency"))),
            func.count(),
        ).where(
            ItemCard.status == CardStatus.READY, ItemCard.generated_at >= now - timedelta(hours=24)
        )
    ).one()
    return Coverage(
        model_id=model.id if model else None,
        trained_at=model.trained_at if model else None,
        auc=model.auc if model else None,
        samples=model.samples if model else 0,
        scored_waiting=int(waiting or 0),
        top_carded_24h=round(window[0] / window[1], 3) if window[1] else None,
        dx_share_24h=round(share[0] / share[1], 3) if share[1] else None,
    )
