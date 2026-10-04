"""Technology registry: keyword → canonical key at write time, labels, seeding, candidates.

Card keywords are free text. `ItemCard.technology_keys` holds their canonical keys, computed
whenever a card's keywords are written (a before_flush hook), so the radar groups on a
GIN-indexed array instead of normalising every keyword on every request (checklist KW-1).
"""

import logging
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item
from news_insight.technologies.catalog import TechCatalog, TechStatus, normalize
from news_insight.technologies.models import KeywordLabel, Technology, TechnologyAlias

log = logging.getLogger(__name__)


def canonical_keys(keywords: Iterable[str], aliases: dict[str, str]) -> list[str]:
    """Python twin of the `canonical_keyword_keys` SQL function (tests, fixtures)."""
    keys: list[str] = []
    for word in keywords:
        key = normalize(word)
        if not key:
            continue
        key = aliases.get(key, key)
        if key not in keys:
            keys.append(key)
    return keys


def alias_map(session: Session) -> dict[str, str]:
    return dict(
        session.execute(select(TechnologyAlias.alias, TechnologyAlias.technology_key))
        .tuples()
        .all()
    )


def recompute_all(session: Session) -> int:
    """Re-derive technology_keys after registry edits (one statement). Returns changed rows."""
    result = session.execute(
        text(
            "UPDATE item_cards SET technology_keys = canonical_keyword_keys(keywords) "
            "WHERE technology_keys IS DISTINCT FROM canonical_keyword_keys(keywords)"
        )
    )
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


def refresh_labels(session: Session, *, now: datetime, days: int = 180) -> int:
    """keyword_labels ← the most common spelling of each key over recent cards."""
    aliases = alias_map(session)
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    rows = session.execute(
        select(ItemCard.keywords)
        .join(Item, Item.id == ItemCard.item_id)
        .where(
            ItemCard.status == CardStatus.READY, Item.first_seen_at >= now - timedelta(days=days)
        )
    ).scalars()
    for keywords in rows:
        for word in keywords or []:
            key = normalize(word)
            if key:
                spellings[aliases.get(key, key)][word.strip().lstrip("#")[:120]] += 1
    session.execute(delete(KeywordLabel))
    session.add_all(
        KeywordLabel(key=key[:80], label=counter.most_common(1)[0][0], cards=sum(counter.values()))
        for key, counter in spellings.items()
    )
    session.flush()
    return len(spellings)


def labels_for(session: Session, keys: Iterable[str]) -> dict[str, str]:
    """Display labels: registry label, else the most common spelling, else the key."""
    wanted = list(dict.fromkeys(keys))
    if not wanted:
        return {}
    labels = dict(
        session.execute(
            select(KeywordLabel.key, KeywordLabel.label).where(KeywordLabel.key.in_(wanted))
        )
        .tuples()
        .all()
    )
    labels.update(
        session.execute(select(Technology.key, Technology.label).where(Technology.key.in_(wanted)))
        .tuples()
        .all()
    )
    return {key: labels.get(key, key) for key in wanted}


@dataclass
class SeedResult:
    created: int = 0
    updated: int = 0
    aliases_added: int = 0


def seed_registry(session: Session, catalog: TechCatalog) -> SeedResult:
    """Upsert the bundled seed. Rows edited in the console keep their label, theme and status;
    seed aliases are added but console-added aliases are never removed."""
    result = SeedResult()
    existing = {tech.key: tech for tech in session.scalars(select(Technology))}
    owned = dict(
        session.execute(select(TechnologyAlias.alias, TechnologyAlias.technology_key))
        .tuples()
        .all()
    )
    for entry in catalog.technologies:
        tech = existing.get(entry.key)
        if tech is None:
            session.add(
                Technology(
                    key=entry.key,
                    label=entry.label,
                    theme_key=entry.theme,
                    kind=entry.kind,
                    status=entry.status,
                )
            )
            result.created += 1
        elif not tech.edited_in_console and (
            (tech.label, tech.theme_key, tech.kind, tech.status)
            != (entry.label, entry.theme, entry.kind, entry.status)
        ):
            tech.label, tech.theme_key, tech.kind, tech.status = (
                entry.label,
                entry.theme,
                entry.kind,
                entry.status,
            )
            result.updated += 1
    session.flush()
    for entry in catalog.technologies:
        for alias in entry.aliases:
            if alias not in owned:
                session.add(TechnologyAlias(alias=alias, technology_key=entry.key))
                owned[alias] = entry.key
                result.aliases_added += 1
    session.flush()
    return result


def candidates(
    session: Session, *, now: datetime, days: int = 30, min_count: int = 10, limit: int = 100
) -> list[tuple[str, int]]:
    """Frequent keys on DX-relevant cards that the registry does not know (or ignore)."""
    element = (
        func.jsonb_array_elements_text(ItemCard.technology_keys).table_valued("value").alias("tk")
    )
    key = element.c.value
    known = select(Technology.key)
    rows = session.execute(
        select(key, func.count())
        .select_from(ItemCard)
        .join(Item, Item.id == ItemCard.item_id)
        .join(element, text("true"))
        .where(
            ItemCard.status == CardStatus.READY,
            ItemCard.scope.in_(["dx", "dx_dependency"]),
            Item.first_seen_at >= now - timedelta(days=days),
            key.not_in(known),
        )
        .group_by(key)
        .having(func.count() >= min_count)
        .order_by(func.count().desc())
        .limit(limit)
    ).tuples()
    return [(str(k), int(c)) for k, c in rows]


def is_known_status(status: str) -> bool:
    return status in {s.value for s in TechStatus}
