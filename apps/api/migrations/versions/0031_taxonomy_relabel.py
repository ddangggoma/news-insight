"""One relabelling function for cards: legacy, llm, rule and derived labels (plan 15-2).

`relabel_items(ids)` recomputes every non-human label of the given cards:
- legacy: the LLM columns (themes, the field when there is no theme, signal type, impact,
  scope) on active nodes;
- llm: `item_cards.extra_labels` ({scheme: [node keys]}) for schemes without a column;
- rule: active nodes deeper than their scheme's `llm_depth` whose key or an alias is one of
  the card's keyword keys (`technology_keys`) — 15-1 also matched shallow nodes, so the
  keyword "AI" put 379 cards on the field node "ai";
- derived: `implies` relations from a labelled node or any of its ancestors.
The card trigger and the console's change engine both call it.

Revision ID: 0031
Revises: 0030
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

NODE_KEYS_VIEW = """
CREATE OR REPLACE VIEW tax_node_keys AS
  SELECT id AS node_id, key AS match_key FROM tax_nodes
  UNION
  SELECT id, a.value FROM tax_nodes, jsonb_array_elements_text(aliases) AS a(value)
"""

RELABEL_FUNCTION = """
CREATE OR REPLACE FUNCTION relabel_items(ids integer[]) RETURNS void
LANGUAGE sql AS $$
  DELETE FROM card_labels
   WHERE item_id = ANY(ids) AND source IN ('legacy', 'llm', 'rule', 'derived');

  INSERT INTO card_labels (item_id, node_id, scheme_id, source)
  SELECT v.item_id, n.id, n.scheme_id, v.source
  FROM (
    SELECT c.item_id, 'technology' AS scheme, t.value AS node, 'legacy' AS source
      FROM item_cards c, jsonb_array_elements_text(coalesce(c.themes, '[]'::jsonb)) AS t(value)
     WHERE c.item_id = ANY(ids)
    UNION ALL
    SELECT item_id, 'technology', field, 'legacy' FROM item_cards
     WHERE item_id = ANY(ids) AND field IS NOT NULL
       AND jsonb_array_length(coalesce(themes, '[]'::jsonb)) = 0
    UNION ALL
    SELECT item_id, 'signal_type', signal_type, 'legacy' FROM item_cards
     WHERE item_id = ANY(ids) AND signal_type IS NOT NULL
    UNION ALL
    SELECT item_id, 'impact', impact, 'legacy' FROM item_cards
     WHERE item_id = ANY(ids) AND impact IS NOT NULL
    UNION ALL
    SELECT item_id, 'scope', scope, 'legacy' FROM item_cards
     WHERE item_id = ANY(ids) AND scope IS NOT NULL
    UNION ALL
    SELECT c.item_id, e.key, k.value, 'llm'
      FROM item_cards c,
           jsonb_each(coalesce(c.extra_labels, '{}'::jsonb)) AS e(key, value),
           jsonb_array_elements_text(CASE WHEN jsonb_typeof(e.value) = 'array'
                                          THEN e.value ELSE '[]'::jsonb END) AS k(value)
     WHERE c.item_id = ANY(ids)
  ) v
  JOIN tax_schemes s ON s.key = v.scheme
  JOIN tax_nodes n ON n.scheme_id = s.id AND n.key = v.node AND n.status = 'active'
  ON CONFLICT (item_id, node_id) DO NOTHING;

  INSERT INTO card_labels (item_id, node_id, scheme_id, source)
  SELECT DISTINCT c.item_id, n.id, n.scheme_id, 'rule'
  FROM item_cards c
  CROSS JOIN LATERAL jsonb_array_elements_text(coalesce(c.technology_keys, '[]'::jsonb)) AS k(value)
  JOIN tax_node_keys nk ON nk.match_key = k.value
  JOIN tax_nodes n ON n.id = nk.node_id AND n.status = 'active'
  JOIN tax_schemes s ON s.id = n.scheme_id
   AND s.assign ? 'rule' AND n.depth > coalesce(s.llm_depth, 0)
  WHERE c.item_id = ANY(ids)
  ON CONFLICT (item_id, node_id) DO NOTHING;

  INSERT INTO card_labels (item_id, node_id, scheme_id, source)
  SELECT DISTINCT l.item_id, target.id, target.scheme_id, 'derived'
  FROM card_labels l
  JOIN tax_nodes n ON n.id = l.node_id
  JOIN tax_relations r ON r.kind = 'implies' AND r.from_node_id = ANY(n.path)
  JOIN tax_nodes target ON target.id = r.to_node_id AND target.status = 'active'
  WHERE l.item_id = ANY(ids) AND l.source <> 'derived'
  ON CONFLICT (item_id, node_id) DO NOTHING;
$$
"""

TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION item_cards_sync_labels() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM relabel_items(ARRAY[NEW.item_id]);
  RETURN NULL;
END
$$
"""

TRIGGER_COLUMNS = (
    "field, themes, technology_keys, keywords, signal_type, impact, scope, extra_labels"
)


def upgrade() -> None:
    op.add_column(
        "item_cards",
        sa.Column(
            "extra_labels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column("tax_schemes", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "tax_schemes",
        sa.Column(
            "assign",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='["llm"]',
            nullable=False,
        ),
    )
    op.execute(NODE_KEYS_VIEW)
    op.execute(RELABEL_FUNCTION)
    op.execute(TRIGGER_FUNCTION)
    op.execute("DROP TRIGGER IF EXISTS item_cards_sync_labels ON item_cards")
    op.execute(
        f"CREATE TRIGGER item_cards_sync_labels AFTER INSERT OR UPDATE OF {TRIGGER_COLUMNS} "
        "ON item_cards FOR EACH ROW EXECUTE FUNCTION item_cards_sync_labels()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS item_cards_sync_labels ON item_cards")
    op.execute("DROP FUNCTION IF EXISTS item_cards_sync_labels()")
    op.execute("DROP FUNCTION IF EXISTS relabel_items(integer[])")
    op.execute("DROP VIEW IF EXISTS tax_node_keys")
    op.drop_column("tax_schemes", "assign")
    op.drop_column("tax_schemes", "description")
    op.drop_column("item_cards", "extra_labels")
