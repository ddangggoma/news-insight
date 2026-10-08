"""The schemes and their node trees as the API serves them (plan 15-1)."""

from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.taxonomy.models import TaxNode, TaxRevision, TaxScheme


class NodeOut(BaseModel):
    id: int
    key: str
    label: str
    parent_id: int | None
    depth: int
    status: str
    sort: int


class NodeDetail(NodeOut):
    definition: str | None
    include_text: str | None
    exclude_text: str | None
    aliases: list[str]
    attrs: dict[str, Any]
    merged_into_id: int | None
    edited_in_console: bool


class SchemeOut(BaseModel):
    key: str
    name: str
    structure: str
    min_labels: int
    max_labels: int
    llm_depth: int | None
    level_names: list[str]
    uses: list[str]
    nodes: list[NodeOut] | list[NodeDetail]


class TaxonomyOut(BaseModel):
    revision: int | None
    schemes: list[SchemeOut]


def taxonomy_view(session: Session, *, detail: bool = False) -> TaxonomyOut:
    """Flat node lists (parents before children by depth, then sort); readers get active nodes."""
    revision = session.scalar(
        select(func.max(TaxRevision.id)).where(TaxRevision.status == "applied")
    )
    schemes = list(
        session.scalars(
            select(TaxScheme)
            .where(TaxScheme.status == "active")
            .order_by(TaxScheme.sort, TaxScheme.id)
        )
    )
    statement = select(TaxNode).order_by(TaxNode.depth, TaxNode.sort, TaxNode.id)
    if not detail:
        statement = statement.where(TaxNode.status == "active")
    by_scheme: dict[int, list[TaxNode]] = {}
    for node in session.scalars(statement):
        by_scheme.setdefault(node.scheme_id, []).append(node)
    model = NodeDetail if detail else NodeOut
    return TaxonomyOut(
        revision=revision,
        schemes=[
            SchemeOut(
                key=s.key,
                name=s.name,
                structure=s.structure,
                min_labels=s.min_labels,
                max_labels=s.max_labels,
                llm_depth=s.llm_depth,
                level_names=list(s.level_names or []),
                uses=list(s.uses or []),
                nodes=[
                    model.model_validate(n, from_attributes=True) for n in by_scheme.get(s.id, [])
                ],
            )
            for s in schemes
        ],
    )
