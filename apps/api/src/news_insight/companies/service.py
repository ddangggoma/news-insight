"""Company registry: seeding, card company keys and the queue of names it does not know.

`ItemCard.company_keys` is derived in the database (`canonical_company_keys`, a trigger on
`companies` and `keywords`) from the engine's company list and the card keywords, so every write
path agrees; registry edits are applied to existing cards with `recompute_all`.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.companies.catalog import CompanyCatalog, CompanyStatus
from news_insight.companies.models import Company, CompanyAlias
from news_insight.content.models import Item
from news_insight.technologies.catalog import normalize

RELEVANT_SCOPES = ("dx", "dx_dependency")


def canonical_keys(names: Iterable[str], aliases: dict[str, str]) -> list[str]:
    """Python twin of the `canonical_company_keys` SQL function (tests, fixtures)."""
    keys: list[str] = []
    for name in names:
        key = aliases.get(normalize(name))
        if key is not None and key not in keys:
            keys.append(key)
    return keys


def alias_map(session: Session) -> dict[str, str]:
    return dict(
        session.execute(select(CompanyAlias.alias, CompanyAlias.company_key)).tuples().all()
    )


def recompute_all(session: Session) -> int:
    """Re-derive company_keys after registry edits (one statement). Returns changed rows."""
    result = session.execute(
        text(
            "UPDATE item_cards SET company_keys = canonical_company_keys(companies, keywords) "
            "WHERE company_keys IS DISTINCT FROM canonical_company_keys(companies, keywords)"
        )
    )
    session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


@dataclass
class SeedResult:
    created: int = 0
    updated: int = 0
    aliases_added: int = 0


def seed_registry(session: Session, catalog: CompanyCatalog) -> SeedResult:
    """Upsert the bundled seed. Rows edited in the console keep their fields; seed names are
    added but console-added aliases are never removed."""
    result = SeedResult()
    existing = {company.key: company for company in session.scalars(select(Company))}
    for entry in catalog.companies:
        values = {
            "name": entry.name,
            "name_ko": entry.name_ko,
            "kind": entry.kind,
            "region": entry.region,
            "relation": entry.relation,
            "themes": entry.themes,
            "domains": entry.domains,
            "status": entry.status,
        }
        company = existing.get(entry.key)
        if company is None:
            session.add(Company(key=entry.key, **values))
            result.created += 1
        elif not company.edited_in_console and any(
            getattr(company, field) != value for field, value in values.items()
        ):
            for field, value in values.items():
                setattr(company, field, value)
            result.updated += 1
    session.flush()
    owned = alias_map(session)
    for entry in catalog.companies:
        for name in entry.match_names:
            if name not in owned:
                session.add(CompanyAlias(alias=name, company_key=entry.key))
                owned[name] = entry.key
                result.aliases_added += 1
    session.flush()
    return result


@dataclass(frozen=True)
class CompanyInfo:
    key: str
    name: str
    name_ko: str | None
    kind: str
    region: str
    relation: str
    themes: list[str]
    domains: list[str]


def info_for(session: Session, keys: Iterable[str] | None = None) -> dict[str, CompanyInfo]:
    """Registry rows (all of them without `keys`), ignored companies left out."""
    statement = select(Company).where(Company.status != CompanyStatus.IGNORED)
    if keys is not None:
        wanted = list(dict.fromkeys(keys))
        if not wanted:
            return {}
        statement = statement.where(Company.key.in_(wanted))
    return {
        c.key: CompanyInfo(
            key=c.key,
            name=c.name,
            name_ko=c.name_ko,
            kind=c.kind.value,
            region=c.region.value,
            relation=c.relation.value,
            themes=list(c.themes or []),
            domains=list(c.domains or []),
        )
        for c in session.scalars(statement)
    }


@dataclass(frozen=True)
class Candidate:
    name: str  # the most common spelling
    key: str  # normalised
    cards: int
    sources: int
    earlier: int  # cards in the lookback before the window


def candidates(
    session: Session,
    *,
    now: datetime,
    days: int = 30,
    lookback_days: int = 90,
    min_count: int = 3,
    min_sources: int = 2,
    limit: int = 100,
) -> list[Candidate]:
    """Company names the engine wrote on DX-relevant cards that the registry does not know.

    `earlier == 0` marks a name that was not reported at all in the lookback before the window:
    a new entrant rather than a company the registry simply misses."""
    start = now - timedelta(days=days)
    element = func.jsonb_array_elements_text(ItemCard.companies).table_valued("value").alias("c")
    rows = session.execute(
        select(element.c.value, Item.source_id, Item.first_seen_at)
        .select_from(ItemCard)
        .join(Item, Item.id == ItemCard.item_id)
        .join(element, text("true"))
        .where(
            ItemCard.status == CardStatus.READY,
            ItemCard.scope.in_(RELEVANT_SCOPES),
            Item.first_seen_at >= start - timedelta(days=lookback_days),
            Item.first_seen_at < now,
        )
    ).tuples()
    known = set(alias_map(session))
    spellings: dict[str, Counter[str]] = {}
    sources: dict[str, set[int]] = {}
    earlier: Counter[str] = Counter()
    for name, source_id, seen in rows:
        key = normalize(str(name))
        if len(key) < 2 or key in known:
            continue
        if seen < start:
            earlier[key] += 1
            continue
        spellings.setdefault(key, Counter())[str(name).strip()] += 1
        sources.setdefault(key, set()).add(int(source_id))
    found = [
        Candidate(
            name=counter.most_common(1)[0][0],
            key=key,
            cards=sum(counter.values()),
            sources=len(sources[key]),
            earlier=earlier[key],
        )
        for key, counter in spellings.items()
        if sum(counter.values()) >= min_count and len(sources[key]) >= min_sources
    ]
    found.sort(key=lambda c: (-c.cards, -c.sources, c.key))
    return found[:limit]
