"""Card classification (item labels by taxonomy axis) and canonical keywords.

The taxonomy itself stays in catalog/taxonomy.yaml (no taxonomy_nodes table): every label
row records the taxonomy revision it was assigned under.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

CURRENT = sa.text("superseded_at IS NULL")


def upgrade() -> None:
    op.add_column("item_cards", sa.Column("taxonomy_rev", sa.Integer(), nullable=True))
    op.create_table(
        "item_labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column(
            "axis",
            sa.Enum("field", "product", "impact", name="axis", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("node_key", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "method",
            sa.Enum("llm", "rule", name="labelmethod", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("taxonomy_rev", sa.Integer(), nullable=False),
        sa.Column("engine", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("labeled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_item_labels_item_id_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_labels")),
    )
    op.create_index(
        "uq_item_labels_current",
        "item_labels",
        ["item_id", "axis", "node_key"],
        unique=True,
        postgresql_where=CURRENT,
    )
    op.create_index(
        "ix_item_labels_current_node",
        "item_labels",
        ["axis", "node_key"],
        unique=False,
        postgresql_where=CURRENT,
    )
    op.create_table(
        "keywords",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical", sa.String(length=80), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_keywords")),
        sa.UniqueConstraint("canonical", name=op.f("uq_keywords_canonical")),
    )
    op.create_table(
        "keyword_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=80), nullable=False),
        sa.Column("keyword_id", sa.Integer(), nullable=False),
        sa.Column(
            "origin",
            sa.Enum("seed", "auto", name="aliasorigin", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name=op.f("fk_keyword_aliases_keyword_id_keywords"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_keyword_aliases")),
        sa.UniqueConstraint("alias", name=op.f("uq_keyword_aliases_alias")),
    )
    op.create_index(
        op.f("ix_keyword_aliases_keyword_id"), "keyword_aliases", ["keyword_id"], unique=False
    )
    op.create_table(
        "item_keywords",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("keyword_id", sa.Integer(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_item_keywords_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name=op.f("fk_item_keywords_keyword_id_keywords"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", "keyword_id", name=op.f("pk_item_keywords")),
    )
    op.create_index(
        op.f("ix_item_keywords_keyword_id"), "item_keywords", ["keyword_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_item_keywords_keyword_id"), table_name="item_keywords")
    op.drop_table("item_keywords")
    op.drop_index(op.f("ix_keyword_aliases_keyword_id"), table_name="keyword_aliases")
    op.drop_table("keyword_aliases")
    op.drop_table("keywords")
    op.drop_index("ix_item_labels_current_node", table_name="item_labels")
    op.drop_index("uq_item_labels_current", table_name="item_labels")
    op.drop_table("item_labels")
    op.drop_column("item_cards", "taxonomy_rev")
