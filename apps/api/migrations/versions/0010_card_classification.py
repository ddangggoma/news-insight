"""Card classification: field, themes, DX businesses, impact, scope, relevance (P4).

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_cards", sa.Column("field", sa.String(length=40), nullable=True))
    op.add_column(
        "item_cards",
        sa.Column(
            "themes", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
    )
    op.add_column(
        "item_cards",
        sa.Column(
            "businesses",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column("item_cards", sa.Column("impact", sa.String(length=20), nullable=True))
    op.add_column("item_cards", sa.Column("scope", sa.String(length=20), nullable=True))
    op.add_column("item_cards", sa.Column("relevance", sa.Integer(), nullable=True))
    op.add_column("item_cards", sa.Column("taxonomy_revision", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_item_cards_field"), "item_cards", ["field"], unique=False)
    op.create_index(op.f("ix_item_cards_scope"), "item_cards", ["scope"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_item_cards_scope"), table_name="item_cards")
    op.drop_index(op.f("ix_item_cards_field"), table_name="item_cards")
    op.drop_column("item_cards", "taxonomy_revision")
    op.drop_column("item_cards", "relevance")
    op.drop_column("item_cards", "scope")
    op.drop_column("item_cards", "impact")
    op.drop_column("item_cards", "businesses")
    op.drop_column("item_cards", "themes")
    op.drop_column("item_cards", "field")
