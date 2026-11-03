"""Reader facts: the explore feed, facets and insights read one narrow row per published item.

`reader_facts` (migration 0046) is a materialized view of items joined to their ready card,
source and story, without archive pages and repeats: the fixed part of
`ReaderFilters.conditions()`. The scheduler refreshes it every few minutes
(`reader.refresh_facts`), so a new card reaches the explore page a few minutes later, the way
the web server's five-minute response cache already did. Item pages and the radar still read
the tables themselves.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ColumnElement,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    or_,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from news_insight.public.filters import AXES, SCOPES, ReaderFilters, search_condition
from news_insight.public.periods import Window
from news_insight.taxonomy.catalog import TAXONOMY_TREE
from news_insight.taxonomy.query import labelled_under, parse_ref

# its own metadata: a view, never created or diffed by alembic autogenerate
facts = Table(
    "reader_facts",
    MetaData(),
    Column("item_id", Integer, primary_key=True),
    Column("occurred_at", DateTime(timezone=True)),
    Column("taxonomy_revision", String(20)),
    Column("scope", String(20)),
    Column("field", String(40)),
    Column("signal_type", String(20)),
    Column("impact", String(20)),
    Column("relevance", Integer),
    Column("track", String(32)),
    Column("region", String(32)),
    Column("themes", JSONB),
    Column("technology_keys", JSONB),
    Column("company_keys", JSONB),
    Column("story_id", BigInteger),
    Column("is_representative", Boolean),
    Column("source_count", Integer),
    Column("title_ko", Text),
    Column("title", Text),
    Column("keywords_text", Text),
)
F = facts.c

# facet axis -> its column (theme is a JSON array, counted separately)
AXIS_COLUMNS = {
    "field": F.field,
    "signal": F.signal_type,
    "impact": F.impact,
    "track": F.track,
    "region": F.region,
}


def refresh(session: Session, *, concurrently: bool = True) -> None:
    """Rebuild the view; CONCURRENTLY keeps it readable meanwhile (a few seconds)."""
    mode = " CONCURRENTLY" if concurrently else ""
    session.execute(text(f"REFRESH MATERIALIZED VIEW{mode} reader_facts"))


def in_window(window: Window) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [F.occurred_at < window.end]
    if window.start is not None:
        conditions.append(F.occurred_at >= window.start)
    return conditions


def axis_condition(axis: str, chosen: tuple[str, ...]) -> ColumnElement[bool]:
    if axis == "theme":
        return or_(*(F.themes.contains([value]) for value in chosen))
    if axis == "company":
        return or_(*(F.company_keys.contains([value]) for value in chosen))
    if axis == "node":
        refs = tuple(ref for v in chosen if (ref := parse_ref(v)) is not None)
        return F.item_id.in_(labelled_under(refs))
    return AXIS_COLUMNS[axis].in_(chosen)


def common(filters: ReaderFilters) -> list[ColumnElement[bool]]:
    """What every count shares: the current tree, the search, companies and nodes."""
    conditions: list[ColumnElement[bool]] = [F.taxonomy_revision.like(f"{TAXONOMY_TREE}.%")]
    for axis, chosen in filters.values.items():
        if axis not in AXES:
            conditions.append(axis_condition(axis, chosen))
    if filters.q:
        conditions.append(search_condition(filters.q, (F.title_ko, F.title, F.keywords_text)))
    return conditions


def narrowing(
    filters: ReaderFilters, *, skip: str | None = None, scoped: bool = True
) -> list[ColumnElement[bool]]:
    """The scope and the facet axes, one axis left out (see ReaderFilters.conditions)."""
    conditions: list[ColumnElement[bool]] = []
    scopes = SCOPES[filters.scope]
    if scoped and scopes is not None:
        conditions.append(F.scope.in_(scopes))
    for axis, chosen in filters.values.items():
        if axis in AXES and axis != skip:
            conditions.append(axis_condition(axis, chosen))
    return conditions


def conditions(filters: ReaderFilters) -> list[ColumnElement[bool]]:
    """`ReaderFilters.conditions()` on the view."""
    return [*common(filters), *narrowing(filters)]
