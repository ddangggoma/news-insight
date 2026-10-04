"""Relevance review: reproducible random samples, labels, stats and CSV export."""

import csv
import io
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import case, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.console.queries import card_body, item_rows
from news_insight.console.schemas import CardBody, ItemRow
from news_insight.content.models import Item
from news_insight.review.models import RelevanceReview, Verdict
from news_insight.sources.enums import Track
from news_insight.sources.models import Source


class ReviewOut(BaseModel):
    verdict: Verdict
    note: str | None
    reviewed_at: datetime


class ReviewItem(BaseModel):
    item: ItemRow
    card: CardBody | None
    review: ReviewOut | None


class ReviewSample(BaseModel):
    seed: str
    items: list[ReviewItem]
    reviewed: int


class ReviewBody(BaseModel):
    item_id: int
    verdict: Verdict
    note: str | None = Field(default=None, max_length=500)
    seed: str | None = Field(default=None, max_length=40)


class Bucket(BaseModel):
    key: str
    total: int
    relevant: int
    irrelevant: int
    unsure: int

    @property
    def rate(self) -> float:
        decided = self.relevant + self.irrelevant
        return self.relevant / decided if decided else 0.0


class Agreement(BaseModel):
    """Operator verdict vs LLM scope (dx/dx_dependency = relevant), unsure excluded."""

    tp: int
    fp: int
    fn: int
    tn: int
    precision: float | None
    recall: float | None
    accuracy: float | None


class ReviewStats(BaseModel):
    classifier: Agreement
    overall: Bucket
    by_track: list[Bucket]
    by_category: list[Bucket]
    worst_sources: list[Bucket]


def sample(
    session: Session,
    *,
    seed: str,
    size: int,
    track: Track | None,
    days: int | None,
    now: datetime,
) -> ReviewSample:
    """Deterministic for a seed: ORDER BY md5(seed || id). Items with Korean cards only."""
    conditions = [ItemCard.status == CardStatus.READY]
    if track is not None:
        conditions.append(Item.track == track)
    if days:
        conditions.append(Item.first_seen_at >= now - timedelta(days=days))
    rows = list(
        session.execute(
            select(Item, Source, ItemCard, RelevanceReview)
            .join(Source, Source.id == Item.source_id)
            .join(ItemCard, ItemCard.item_id == Item.id)
            .outerjoin(RelevanceReview, RelevanceReview.item_id == Item.id)
            .where(*conditions)
            .order_by(func.md5(func.concat(seed, Item.id)))
            .limit(size)
        ).tuples()
    )
    items = item_rows(session, [(item, source) for item, source, _, _ in rows])
    views = [
        ReviewItem(
            item=row,
            card=card_body(card),
            review=ReviewOut(verdict=rev.verdict, note=rev.note, reviewed_at=rev.reviewed_at)
            if rev
            else None,
        )
        for row, (_, _, card, rev) in zip(items, rows, strict=True)
    ]
    return ReviewSample(seed=seed, items=views, reviewed=sum(1 for v in views if v.review))


def record(session: Session, body: ReviewBody, *, now: datetime) -> ReviewOut:
    if session.get(Item, body.item_id) is None:
        raise LookupError(f"unknown item {body.item_id}")
    values = {
        "item_id": body.item_id,
        "verdict": body.verdict,
        "note": body.note or None,
        "sample_seed": body.seed,
        "reviewed_at": now,
    }
    statement = insert(RelevanceReview).values(**values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["item_id"],
            set_={
                key: statement.excluded[key]
                for key in ("verdict", "note", "sample_seed", "reviewed_at")
            },
        )
    )
    session.flush()
    return ReviewOut(verdict=body.verdict, note=body.note or None, reviewed_at=now)


def _buckets(
    session: Session, column: Any, *, limit: int | None = None, worst: bool = False
) -> list[Bucket]:
    relevant = func.count(case((RelevanceReview.verdict == Verdict.RELEVANT, 1)))
    irrelevant = func.count(case((RelevanceReview.verdict == Verdict.IRRELEVANT, 1)))
    unsure = func.count(case((RelevanceReview.verdict == Verdict.UNSURE, 1)))
    statement = (
        select(column, func.count(), relevant, irrelevant, unsure)
        .select_from(RelevanceReview)
        .join(Item, Item.id == RelevanceReview.item_id)
        .join(Source, Source.id == Item.source_id)
        .group_by(column)
    )
    if worst:
        statement = statement.having(irrelevant > 0).order_by(
            irrelevant.desc(), func.count().desc()
        )
    else:
        statement = statement.order_by(func.count().desc())
    if limit:
        statement = statement.limit(limit)
    return [
        Bucket(
            key=str(key.value if hasattr(key, "value") else key),
            total=t,
            relevant=r,
            irrelevant=i,
            unsure=u,
        )
        for key, t, r, i, u in session.execute(statement).tuples()
    ]


def agreement(session: Session) -> Agreement:
    rows = session.execute(
        select(RelevanceReview.verdict, ItemCard.scope)
        .join(ItemCard, ItemCard.item_id == RelevanceReview.item_id)
        .where(RelevanceReview.verdict != Verdict.UNSURE, ItemCard.scope.is_not(None))
    ).tuples()
    tp = fp = fn = tn = 0
    for verdict, scope in rows:
        predicted = scope in ("dx", "dx_dependency")
        actual = verdict is Verdict.RELEVANT
        tp += predicted and actual
        fp += predicted and not actual
        fn += (not predicted) and actual
        tn += (not predicted) and not actual
    total = tp + fp + fn + tn
    return Agreement(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        accuracy=(tp + tn) / total if total else None,
    )


def stats(session: Session) -> ReviewStats:
    overall = _buckets(session, literal("전체"))
    return ReviewStats(
        classifier=agreement(session),
        overall=overall[0]
        if overall
        else Bucket(key="전체", total=0, relevant=0, irrelevant=0, unsure=0),
        by_track=_buckets(session, Item.track),
        by_category=_buckets(session, Source.category),
        worst_sources=_buckets(session, Source.name, limit=15, worst=True),
    )


def export_csv(session: Session) -> str:
    rows = session.execute(
        select(RelevanceReview, Item, Source, ItemCard)
        .join(Item, Item.id == RelevanceReview.item_id)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .order_by(RelevanceReview.reviewed_at)
    ).tuples()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "item_id",
            "verdict",
            "note",
            "reviewed_at",
            "track",
            "category",
            "region",
            "source",
            "title",
            "title_ko",
            "keywords",
            "url",
            "sample_seed",
        ]
    )
    for review, item, source, card in rows:
        writer.writerow(
            [
                item.id,
                review.verdict.value,
                review.note or "",
                review.reviewed_at.isoformat(),
                item.track.value,
                source.category,
                source.region.value,
                source.name,
                item.title,
                card.title_ko if card else "",
                " ".join(card.keywords) if card else "",
                item.url,
                review.sample_seed or "",
            ]
        )
    return "﻿" + buffer.getvalue()  # BOM so Excel opens Korean text correctly
