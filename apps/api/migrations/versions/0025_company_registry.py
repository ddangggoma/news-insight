"""Company registry and card company tags (plan 12).

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# registered companies named in a card's `companies` (engine output) or `keywords`, in order
CANONICAL_FUNCTION = r"""
CREATE OR REPLACE FUNCTION canonical_company_keys(companies jsonb, keywords jsonb) RETURNS jsonb
LANGUAGE sql STABLE AS $$
  SELECT coalesce(jsonb_agg(company_key ORDER BY pos), '[]'::jsonb) FROM (
    SELECT a.company_key, min(n.pos) AS pos
    FROM (
      SELECT lower(regexp_replace(ltrim(btrim(e.value), '#'), '[\s\-_·]', '', 'g')) AS k, e.pos
      FROM jsonb_array_elements_text(coalesce(companies, '[]'::jsonb))
           WITH ORDINALITY AS e(value, pos)
      UNION ALL
      SELECT lower(regexp_replace(ltrim(btrim(e.value), '#'), '[\s\-_·]', '', 'g')), 100 + e.pos
      FROM jsonb_array_elements_text(coalesce(keywords, '[]'::jsonb))
           WITH ORDINALITY AS e(value, pos)
    ) n
    JOIN company_aliases a ON a.alias = n.k
    GROUP BY a.company_key
  ) d
$$
"""
TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION item_cards_company_keys() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.company_keys := canonical_company_keys(NEW.companies, NEW.keywords);
  RETURN NEW;
END
$$
"""

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("name_ko", sa.String(length=120), nullable=True),
        sa.Column(
            "kind",
            _enum("companykind", "company", "startup", "institute", "regulator", "standards_body"),
            nullable=False,
        ),
        sa.Column(
            "region",
            _enum("companyregion", "kr", "us", "cn", "jp", "tw", "eu", "other"),
            nullable=False,
        ),
        sa.Column(
            "relation",
            _enum("relation", "self", "competitor", "supplier", "partner", "peer"),
            nullable=False,
        ),
        sa.Column(
            "themes", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column(
            "domains", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("status", _enum("companystatus", "active", "watch", "ignored"), nullable=False),
        sa.Column("edited_in_console", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_companies")),
    )
    op.create_table(
        "company_aliases",
        sa.Column("alias", sa.String(length=80), nullable=False),
        sa.Column("company_key", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_key"],
            ["companies.key"],
            name=op.f("fk_company_aliases_company_key_companies"),
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("alias", name=op.f("pk_company_aliases")),
    )
    op.create_index(op.f("ix_company_aliases_company_key"), "company_aliases", ["company_key"])
    for column in ("companies", "company_keys"):
        op.add_column(
            "item_cards",
            sa.Column(
                column, postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
            ),
        )
    op.create_index(
        "ix_item_cards_company_keys", "item_cards", ["company_keys"], postgresql_using="gin"
    )
    op.execute(CANONICAL_FUNCTION)
    op.execute(TRIGGER_FUNCTION)
    op.execute(
        "CREATE TRIGGER item_cards_company_keys BEFORE INSERT OR UPDATE OF companies, keywords "
        "ON item_cards FOR EACH ROW EXECUTE FUNCTION item_cards_company_keys()"
    )
    # card keys are filled by `news-insight companies seed` once the registry has rows


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS item_cards_company_keys ON item_cards")
    op.execute("DROP FUNCTION IF EXISTS item_cards_company_keys()")
    op.execute("DROP FUNCTION IF EXISTS canonical_company_keys(jsonb, jsonb)")
    op.drop_index("ix_item_cards_company_keys", table_name="item_cards")
    op.drop_column("item_cards", "company_keys")
    op.drop_column("item_cards", "companies")
    op.drop_index(op.f("ix_company_aliases_company_key"), table_name="company_aliases")
    op.drop_table("company_aliases")
    op.drop_table("companies")
