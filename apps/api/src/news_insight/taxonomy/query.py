"""Cards under a node of any scheme and depth (plan 15-4): `scheme:key` references."""

import re

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.orm import aliased

from news_insight.content.models import Item
from news_insight.taxonomy.models import CardLabel, TaxNode, TaxScheme

NODE_REF = re.compile(r"^([a-z][a-z0-9_]{1,39}):(\S{1,80})$")


def parse_ref(value: str) -> tuple[str, str] | None:
    match = NODE_REF.match(value.strip())
    return (match[1], match[2]) if match else None


def under_nodes(refs: tuple[tuple[str, str], ...]) -> ColumnElement[bool]:
    """Items labelled on any of these nodes or below them."""
    return Item.id.in_(labelled_under(refs))


def labelled_under(refs: tuple[tuple[str, str], ...]) -> Select[tuple[int]]:
    """Ids of the items labelled on any of these nodes or below them."""
    target = aliased(TaxNode)
    wanted = (
        select(func.array_agg(target.id))
        .join(TaxScheme, TaxScheme.id == target.scheme_id)
        .where(or_(*(and_(TaxScheme.key == s, target.key == k) for s, k in refs)))
        .scalar_subquery()
    )
    return (
        select(CardLabel.item_id)
        .join(TaxNode, TaxNode.id == CardLabel.node_id)
        .where(TaxNode.path.overlap(wanted))
    )
