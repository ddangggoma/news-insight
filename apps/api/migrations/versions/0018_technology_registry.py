"""Technology registry, keyword labels and stored canonical keyword keys (checklist KW-1).

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

CANONICAL_FUNCTION = r"""
CREATE OR REPLACE FUNCTION canonical_keyword_keys(keywords jsonb) RETURNS jsonb
LANGUAGE sql STABLE AS $$
  SELECT coalesce(jsonb_agg(key ORDER BY pos), '[]'::jsonb) FROM (
    SELECT key, min(pos) AS pos FROM (
      SELECT coalesce(a.technology_key, n.k) AS key, n.pos
      FROM (
        SELECT lower(regexp_replace(ltrim(btrim(e.value), '#'), '[\s\-_·]', '', 'g')) AS k, e.pos
        FROM jsonb_array_elements_text(coalesce(keywords, '[]'::jsonb))
             WITH ORDINALITY AS e(value, pos)
      ) n
      LEFT JOIN technology_aliases a ON a.alias = n.k
      WHERE n.k <> ''
    ) m GROUP BY key
  ) d
$$
"""
TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION item_cards_technology_keys() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.technology_keys := canonical_keyword_keys(NEW.keywords);
  RETURN NEW;
END
$$
"""

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "technologies",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("theme_key", sa.String(length=80), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "technology",
                "standard",
                "regulation",
                "product_family",
                name="techkind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "watch", "ignored", name="techstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("edited_in_console", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_technologies")),
    )
    op.create_index(op.f("ix_technologies_theme_key"), "technologies", ["theme_key"])
    op.create_table(
        "technology_aliases",
        sa.Column("alias", sa.String(length=80), nullable=False),
        sa.Column("technology_key", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["technology_key"],
            ["technologies.key"],
            name=op.f("fk_technology_aliases_technology_key_technologies"),
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("alias", name=op.f("pk_technology_aliases")),
    )
    op.create_index(
        op.f("ix_technology_aliases_technology_key"), "technology_aliases", ["technology_key"]
    )
    op.create_table(
        "keyword_labels",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("cards", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_keyword_labels")),
    )
    op.add_column(
        "item_cards",
        sa.Column(
            "technology_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_item_cards_technology_keys", "item_cards", ["technology_keys"], postgresql_using="gin"
    )
    # canonical keys are derived in the database so every write path agrees (KW-1)
    op.execute(CANONICAL_FUNCTION)
    op.execute(TRIGGER_FUNCTION)
    op.execute(
        "CREATE TRIGGER item_cards_technology_keys BEFORE INSERT OR UPDATE OF keywords "
        "ON item_cards FOR EACH ROW EXECUTE FUNCTION item_cards_technology_keys()"
    )
    op.execute("UPDATE item_cards SET technology_keys = canonical_keyword_keys(keywords)")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS item_cards_technology_keys ON item_cards")
    op.execute("DROP FUNCTION IF EXISTS item_cards_technology_keys()")
    op.execute("DROP FUNCTION IF EXISTS canonical_keyword_keys(jsonb)")
    op.drop_index("ix_item_cards_technology_keys", table_name="item_cards")
    op.drop_column("item_cards", "technology_keys")
    op.drop_table("keyword_labels")
    op.drop_index(op.f("ix_technology_aliases_technology_key"), table_name="technology_aliases")
    op.drop_table("technology_aliases")
    op.drop_index(op.f("ix_technologies_theme_key"), table_name="technologies")
    op.drop_table("technologies")
