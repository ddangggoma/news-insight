"""Reader facts: one narrow row per published item for the explore feed, facets and insights.

A materialized view, refreshed every few minutes by the scheduler (public/facts.py). The
explore page ran about 17 aggregate queries per filter change, each joining 0.7 M items to
their cards, sources, stories and repeat checks; this view does those joins once
(2026-11-03: 20-70 s per response).

Additive: code from before this revision never reads it.

Revision ID: 0046
Revises: 0045
"""

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

# Mirrors the fixed part of ReaderFilters.conditions(): a ready card, not an archive page
# (content/freshness.py, ARCHIVE_AFTER = 30 days as hours, like the Python interval), not a
# repeat. The taxonomy tree is filtered when read, so a new tree needs no new view. The
# search columns are copied too: probing the tables per row made the planner scan both
# (2026-11-03: a searched week took longer than before).
VIEW = """
CREATE MATERIALIZED VIEW reader_facts AS
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


def upgrade() -> None:
    op.execute(VIEW)
    # unique: REFRESH ... CONCURRENTLY needs it
    op.execute("CREATE UNIQUE INDEX uq_reader_facts_item_id ON reader_facts (item_id)")
    op.execute("CREATE INDEX ix_reader_facts_occurred_at ON reader_facts (occurred_at)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS reader_facts")
