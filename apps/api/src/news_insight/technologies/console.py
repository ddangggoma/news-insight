"""Console reads and edits for the technology registry (plan 09 §3-3, checklist KW-1).

Every edit marks the row as console-owned (seeding no longer overwrites it) and re-derives
the affected cards' keys in one statement, so the radar reflects it on the next cache miss.
"""

from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item
from news_insight.technologies.catalog import TechKind, TechStatus, normalize
from news_insight.technologies.models import Technology, TechnologyAlias
from news_insight.technologies.service import candidates, labels_for, recompute_all


class RegistryError(ValueError):
    """An edit that would make a key or alias ambiguous."""


class TechnologyOut(BaseModel):
    key: str
    label: str
    theme_key: str | None
    kind: TechKind
    status: TechStatus
    aliases: list[str]
    cards_30d: int
    edited_in_console: bool


class TechnologyIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    key: str | None = Field(default=None, max_length=80)
    theme_key: str | None = Field(default=None, max_length=80)
    kind: TechKind = TechKind.TECHNOLOGY
    status: TechStatus = TechStatus.ACTIVE
    aliases: list[str] = Field(default_factory=list, max_length=50)


class TechnologyPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    theme_key: str | None = None
    kind: TechKind | None = None
    status: TechStatus | None = None
    add_aliases: list[str] = Field(default_factory=list, max_length=50)
    remove_aliases: list[str] = Field(default_factory=list, max_length=50)


class CandidateOut(BaseModel):
    key: str
    label: str
    count: int


def _counts(session: Session, keys: list[str], now: datetime) -> dict[str, int]:
    if not keys:
        return {}
    element = (
        func.jsonb_array_elements_text(ItemCard.technology_keys).table_valued("value").alias("tk")
    )
    rows = session.execute(
        select(element.c.value, func.count())
        .select_from(ItemCard)
        .join(Item, Item.id == ItemCard.item_id)
        .join(element, text("true"))
        .where(
            ItemCard.status == CardStatus.READY,
            Item.first_seen_at >= now - timedelta(days=30),
            element.c.value.in_(keys),
        )
        .group_by(element.c.value)
    ).tuples()
    return {str(k): int(c) for k, c in rows}


def list_technologies(
    session: Session, *, now: datetime, theme: str | None, status: TechStatus | None, q: str | None
) -> list[TechnologyOut]:
    statement = select(Technology)
    if theme:
        statement = statement.where(Technology.theme_key == theme)
    if status is not None:
        statement = statement.where(Technology.status == status)
    if q:
        needle = f"%{normalize(q)}%"
        statement = statement.where(
            Technology.key.like(needle)
            | Technology.label.ilike(f"%{q}%")
            | Technology.key.in_(
                select(TechnologyAlias.technology_key).where(TechnologyAlias.alias.like(needle))
            )
        )
    techs = list(session.scalars(statement.order_by(Technology.theme_key, Technology.label)))
    aliases: dict[str, list[str]] = {}
    for alias, key in session.execute(
        select(TechnologyAlias.alias, TechnologyAlias.technology_key).where(
            TechnologyAlias.technology_key.in_([t.key for t in techs])
        )
    ).tuples():
        aliases.setdefault(key, []).append(alias)
    counts = _counts(session, [t.key for t in techs], now)
    return [
        TechnologyOut(
            key=t.key,
            label=t.label,
            theme_key=t.theme_key,
            kind=t.kind,
            status=t.status,
            aliases=sorted(aliases.get(t.key, [])),
            cards_30d=counts.get(t.key, 0),
            edited_in_console=t.edited_in_console,
        )
        for t in techs
    ]


def _add_aliases(session: Session, key: str, raw: list[str]) -> None:
    for alias in dict.fromkeys(normalize(a) for a in raw):
        if not alias or alias == key:
            continue
        if session.get(Technology, alias) is not None:
            raise RegistryError(f"'{alias}' is itself a technology key")
        owner = session.get(TechnologyAlias, alias)
        if owner is not None and owner.technology_key != key:
            raise RegistryError(f"alias '{alias}' already belongs to {owner.technology_key}")
        if owner is None:
            session.add(TechnologyAlias(alias=alias, technology_key=key))


def create_technology(session: Session, body: TechnologyIn) -> Technology:
    key = normalize(body.key or body.label)
    if not key:
        raise RegistryError("empty key")
    if session.get(Technology, key) is not None:
        raise RegistryError(f"technology '{key}' already exists")
    if session.get(TechnologyAlias, key) is not None:
        raise RegistryError(f"'{key}' is already an alias")
    tech = Technology(
        key=key,
        label=body.label,
        theme_key=body.theme_key,
        kind=body.kind,
        status=body.status,
        edited_in_console=True,
    )
    session.add(tech)
    session.flush()
    _add_aliases(session, key, body.aliases)
    session.flush()
    recompute_all(session)
    return tech


def update_technology(session: Session, key: str, patch: TechnologyPatch) -> Technology:
    tech = session.get(Technology, key)
    if tech is None:
        raise LookupError(key)
    if patch.label is not None:
        tech.label = patch.label
    if "theme_key" in patch.model_fields_set:
        tech.theme_key = patch.theme_key
    if patch.kind is not None:
        tech.kind = patch.kind
    if patch.status is not None:
        tech.status = patch.status
    tech.edited_in_console = True
    _add_aliases(session, key, patch.add_aliases)
    for alias in patch.remove_aliases:
        row = session.get(TechnologyAlias, normalize(alias))
        if row is not None and row.technology_key == key:
            session.delete(row)
    session.flush()
    recompute_all(session)
    return tech


def candidate_list(
    session: Session, *, now: datetime, days: int, min_count: int
) -> list[CandidateOut]:
    rows = candidates(session, now=now, days=days, min_count=min_count)
    labels = labels_for(session, [key for key, _ in rows])
    return [CandidateOut(key=key, label=labels[key], count=count) for key, count in rows]
