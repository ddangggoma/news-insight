"""Classification schemes, nodes of any depth, revisions and card labels (plan 15-1).

`card_labels` rows with source 'legacy' mirror the item_cards columns (field, themes,
technology_keys, signal_type, impact, scope) through a trigger while those columns stay the
source of truth; rule and derived labels added later are left alone.

Revision ID: 0030
Revises: 0029
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# the legacy columns as (scheme key, node key) pairs; the field only when there is no theme
# (a theme already implies its field through the node path)
SYNC_FUNCTION = """
CREATE OR REPLACE FUNCTION item_cards_sync_labels() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  DELETE FROM card_labels WHERE item_id = NEW.item_id AND source = 'legacy';
  INSERT INTO card_labels (item_id, node_id, scheme_id, source)
  SELECT NEW.item_id, n.id, n.scheme_id, 'legacy'
  FROM (
    SELECT 'technology' AS scheme, t.value AS node
      FROM jsonb_array_elements_text(coalesce(NEW.themes, '[]'::jsonb)) AS t(value)
    UNION ALL
    SELECT 'technology', t.value
      FROM jsonb_array_elements_text(coalesce(NEW.technology_keys, '[]'::jsonb)) AS t(value)
    UNION ALL
    SELECT 'technology', NEW.field
      WHERE NEW.field IS NOT NULL AND jsonb_array_length(coalesce(NEW.themes, '[]'::jsonb)) = 0
    UNION ALL SELECT 'signal_type', NEW.signal_type WHERE NEW.signal_type IS NOT NULL
    UNION ALL SELECT 'impact', NEW.impact WHERE NEW.impact IS NOT NULL
    UNION ALL SELECT 'scope', NEW.scope WHERE NEW.scope IS NOT NULL
  ) v
  JOIN tax_schemes s ON s.key = v.scheme
  JOIN tax_nodes n ON n.scheme_id = s.id AND n.key = v.node
  ON CONFLICT (item_id, node_id) DO NOTHING;
  RETURN NULL;
END
$$
"""
revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tax_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("author", sa.String(length=80), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_revisions")),
    )
    op.create_table(
        "tax_schemes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("structure", sa.String(length=10), nullable=False),
        sa.Column("min_labels", sa.Integer(), nullable=False),
        sa.Column("max_labels", sa.Integer(), nullable=False),
        sa.Column("llm_depth", sa.Integer(), nullable=True),
        sa.Column("level_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("uses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_schemes")),
        sa.UniqueConstraint("key", name=op.f("uq_tax_schemes_key")),
    )
    op.create_table(
        "tax_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("include_text", sa.Text(), nullable=True),
        sa.Column("exclude_text", sa.Text(), nullable=True),
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attrs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("merged_into_id", sa.Integer(), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("path", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("edited_in_console", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_id"], ["tax_nodes.id"], name=op.f("fk_tax_nodes_merged_into_id_tax_nodes")
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["tax_nodes.id"], name=op.f("fk_tax_nodes_parent_id_tax_nodes")
        ),
        sa.ForeignKeyConstraint(
            ["scheme_id"], ["tax_schemes.id"], name=op.f("fk_tax_nodes_scheme_id_tax_schemes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_nodes")),
        sa.UniqueConstraint("scheme_id", "key", name="uq_tax_nodes_scheme_key"),
    )
    op.create_index(op.f("ix_tax_nodes_parent_id"), "tax_nodes", ["parent_id"], unique=False)
    op.create_index(
        "ix_tax_nodes_path", "tax_nodes", ["path"], unique=False, postgresql_using="gin"
    )
    op.create_index(op.f("ix_tax_nodes_scheme_id"), "tax_nodes", ["scheme_id"], unique=False)
    op.create_table(
        "card_labels",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("revision_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_card_labels_item_id_items"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["tax_nodes.id"],
            name=op.f("fk_card_labels_node_id_tax_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scheme_id"], ["tax_schemes.id"], name=op.f("fk_card_labels_scheme_id_tax_schemes")
        ),
        sa.PrimaryKeyConstraint("item_id", "node_id", name=op.f("pk_card_labels")),
    )
    op.create_index(op.f("ix_card_labels_node_id"), "card_labels", ["node_id"], unique=False)
    op.create_index(op.f("ix_card_labels_scheme_id"), "card_labels", ["scheme_id"], unique=False)
    op.create_table(
        "tax_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_node_id", sa.Integer(), nullable=False),
        sa.Column("to_node_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_node_id"],
            ["tax_nodes.id"],
            name=op.f("fk_tax_relations_from_node_id_tax_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_node_id"],
            ["tax_nodes.id"],
            name=op.f("fk_tax_relations_to_node_id_tax_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_relations")),
        sa.UniqueConstraint("from_node_id", "to_node_id", "kind", name="uq_tax_relations_pair"),
    )
    op.create_index(
        op.f("ix_tax_relations_to_node_id"), "tax_relations", ["to_node_id"], unique=False
    )
    op.execute(SYNC_FUNCTION)
    # keywords too: technology_keys is set by a BEFORE trigger when only keywords change
    op.execute(
        "CREATE TRIGGER item_cards_sync_labels AFTER INSERT OR UPDATE OF field, themes, "
        "technology_keys, keywords, signal_type, impact, scope ON item_cards "
        "FOR EACH ROW EXECUTE FUNCTION item_cards_sync_labels()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS item_cards_sync_labels ON item_cards")
    op.execute("DROP FUNCTION IF EXISTS item_cards_sync_labels()")
    op.drop_index(op.f("ix_tax_relations_to_node_id"), table_name="tax_relations")
    op.drop_table("tax_relations")
    op.drop_index(op.f("ix_card_labels_scheme_id"), table_name="card_labels")
    op.drop_index(op.f("ix_card_labels_node_id"), table_name="card_labels")
    op.drop_table("card_labels")
    op.drop_index(op.f("ix_tax_nodes_scheme_id"), table_name="tax_nodes")
    op.drop_index("ix_tax_nodes_path", table_name="tax_nodes", postgresql_using="gin")
    op.drop_index(op.f("ix_tax_nodes_parent_id"), table_name="tax_nodes")
    op.drop_table("tax_nodes")
    op.drop_table("tax_schemes")
    op.drop_table("tax_revisions")
