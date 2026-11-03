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


# migration 0046's definition; a change here reaches live with the next rebuild
SELECT = """
SELECT i.id AS item_id,
       coalesce(i.published_at, i.first_seen_at) AS occurred_at,
       c.taxonomy_revision,
       c.scope,
       c.field,
       c.signal_type,
       c.impact,
       c.relevance,
       i.track,
       s.region,
       c.themes,
       c.technology_keys,
       c.company_keys,
       si.story_id,
       st.representative_item_id = i.id AS is_representative,
       st.source_count,
       c.title_ko,
       i.title,
       c.keywords::text AS keywords_text
FROM items i
JOIN sources s ON s.id = i.source_id
JOIN item_cards c ON c.item_id = i.id
LEFT JOIN story_items si ON si.item_id = i.id
LEFT JOIN stories st ON st.id = si.story_id
WHERE c.status = 'ready'
  AND (i.published_at IS NULL OR i.published_at >= i.first_seen_at - interval '720 hours')
  AND NOT EXISTS (
      SELECT 1 FROM item_dedup d WHERE d.item_id = i.id AND d.duplicate_of IS NOT NULL
  )
"""


def refresh(session: Session) -> None:
    """Build the next view beside the live one, then swap it in, in the caller's transaction.

    REFRESH ... CONCURRENTLY compared all 0.5 M rows with the old ones: 34-97 s every three
    minutes (2026-11-04). Building anew takes seconds and readers wait only for the swap; one
    that waits longer than the lock timeout fails this rebuild (LockNotAvailable), and the
    next one tries again.
    """
    for statement in (
        "DROP MATERIALIZED VIEW IF EXISTS reader_facts_next",
        f"CREATE MATERIALIZED VIEW reader_facts_next AS {SELECT}",
        "CREATE UNIQUE INDEX uq_reader_facts_next_item_id ON reader_facts_next (item_id)",
        "CREATE INDEX ix_reader_facts_next_occurred_at ON reader_facts_next (occurred_at)",
        "ANALYZE reader_facts_next",  # a new view has no statistics for the planner
        "SET LOCAL lock_timeout = '3s'",
        "DROP MATERIALIZED VIEW reader_facts",
        "ALTER MATERIALIZED VIEW reader_facts_next RENAME TO reader_facts",
        "ALTER INDEX uq_reader_facts_next_item_id RENAME TO uq_reader_facts_item_id",
        "ALTER INDEX ix_reader_facts_next_occurred_at RENAME TO ix_reader_facts_occurred_at",
    ):
        session.execute(text(statement))


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
