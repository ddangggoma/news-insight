"""Radar distribution over any scheme, depth and base node (plan 15-4b).

Cards in the window (and the window before, for the change) are counted under their label's
ancestor at the chosen depth; a label shallower than the depth counts under itself (a card the
LLM could only place on the field). Reader filters and the period apply as on the radar.
"""

from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, aliased

from news_insight.content.models import Item
from news_insight.public.filters import ReaderFilters, joined
from news_insight.public.periods import Window
from news_insight.taxonomy.models import CardLabel, TaxNode, TaxScheme
from news_insight.taxonomy.query import parse_ref


class DistributionNode(BaseModel):
    key: str
    label: str
    depth: int
    parent_key: str | None
    count: int
    previous: int
    delta: int


class SchemeChoice(BaseModel):
    key: str
    name: str
    max_depth: int
    level_names: list[str]


class Distribution(BaseModel):
    scheme: str
    depth: int
    root: DistributionNode | None
    nodes: list[DistributionNode]
    total: int
    previous_total: int
    schemes: list[SchemeChoice]


class DistributionError(ValueError):
    pass


def distribution(
    session: Session,
    filters: ReaderFilters,
    window: Window,
    *,
    scheme: str,
    depth: int,
    root: str | None,
) -> Distribution:
    schemes = list(
        session.scalars(
            select(TaxScheme).where(TaxScheme.status == "active").order_by(TaxScheme.sort)
        )
    )
    chosen = next((s for s in schemes if s.key == scheme), None)
    if chosen is None:
        raise DistributionError(f"unknown scheme '{scheme}'")
    depths = dict(
        session.execute(
            select(TaxNode.scheme_id, func.max(TaxNode.depth))
            .where(TaxNode.status == "active")
            .group_by(TaxNode.scheme_id)
        )
        .tuples()
        .all()
    )
    base: TaxNode | None = None
    if root:
        ref = parse_ref(root)
        base = (
            session.scalars(
                select(TaxNode).where(
                    TaxNode.scheme_id == chosen.id, TaxNode.key == (ref[1] if ref else "")
                )
            ).one_or_none()
            if ref and ref[0] == scheme
            else None
        )
        if base is None:
            raise DistributionError(f"unknown node '{root}'")
        depth = max(depth, base.depth + 1)
    depth = max(1, min(depth, depths.get(chosen.id, 1)))
    previous = window.previous()
    eligible = (
        joined(select(Item.id.label("item_id"), Item.first_seen_at.label("seen")))
        .where(*filters.conditions(), Item.first_seen_at < window.end)
        .where(Item.first_seen_at >= previous.start if previous.start else Item.id.is_not(None))
        .subquery()
    )
    leaf, bucket = aliased(TaxNode), aliased(TaxNode)
    parent = aliased(TaxNode)
    start = window.start
    current = (
        func.count(distinct(CardLabel.item_id)).filter(eligible.c.seen >= start)
        if start
        else func.count(distinct(CardLabel.item_id))
    )
    before = (
        func.count(distinct(CardLabel.item_id)).filter(eligible.c.seen < start)
        if start
        else func.count(distinct(CardLabel.item_id)) * 0
    )
    statement = (
        select(bucket.key, bucket.label, bucket.depth, parent.key, current, before)
        .select_from(CardLabel)
        .join(eligible, eligible.c.item_id == CardLabel.item_id)
        .join(leaf, leaf.id == CardLabel.node_id)
        .join(bucket, bucket.id == leaf.path[func.least(depth, leaf.depth)])
        .outerjoin(parent, parent.id == bucket.parent_id)
        .where(CardLabel.scheme_id == chosen.id, bucket.status == "active")
        .group_by(bucket.key, bucket.label, bucket.depth, parent.key)
    )
    if base is not None:
        statement = statement.where(leaf.path.contains([base.id]))
    nodes = [
        DistributionNode(
            key=key,
            label=label,
            depth=d,
            parent_key=parent_key,
            count=int(c),
            previous=int(p),
            delta=int(c) - int(p),
        )
        for key, label, d, parent_key, c, p in session.execute(statement).tuples()
        if c or p
    ]
    nodes.sort(key=lambda n: (-n.count, n.key))
    totals = (
        select(
            func.count(distinct(CardLabel.item_id)).filter(eligible.c.seen >= start)
            if start
            else func.count(distinct(CardLabel.item_id)),
            func.count(distinct(CardLabel.item_id)).filter(eligible.c.seen < start)
            if start
            else func.count(distinct(CardLabel.item_id)) * 0,
        )
        .select_from(CardLabel)
        .join(eligible, eligible.c.item_id == CardLabel.item_id)
        .join(leaf, leaf.id == CardLabel.node_id)
        .where(CardLabel.scheme_id == chosen.id)
    )
    if base is not None:
        totals = totals.where(leaf.path.contains([base.id]))
    total, previous_total = session.execute(totals).one()
    return Distribution(
        scheme=scheme,
        depth=depth,
        root=DistributionNode(
            key=base.key,
            label=base.label,
            depth=base.depth,
            parent_key=None,
            count=0,
            previous=0,
            delta=0,
        )
        if base
        else None,
        nodes=nodes,
        total=int(total),
        previous_total=int(previous_total),
        schemes=[
            SchemeChoice(
                key=s.key,
                name=s.name,
                max_depth=int(depths.get(s.id, 1)),
                level_names=list(s.level_names or []),
            )
            for s in schemes
        ],
    )
