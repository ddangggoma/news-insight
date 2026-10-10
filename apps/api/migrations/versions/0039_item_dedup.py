"""Duplicate keys per item, assigned before carding (2026-10-10).

Revision ID: 0039
Revises: 0038
"""

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_dedup",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("url_key", sa.String(length=32), nullable=False),
        sa.Column("text_key", sa.String(length=32), nullable=True),
        sa.Column("title_key", sa.String(length=32), nullable=True),
        sa.Column("lead_key", sa.String(length=32), nullable=True),
        sa.Column("lead_title", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("link_key", sa.String(length=32), nullable=True),
        sa.Column("duplicate_of", sa.Integer(), nullable=True),
        sa.Column("matched_by", sa.String(length=10), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_item_dedup_item_id_items"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of"],
            ["items.id"],
            name=op.f("fk_item_dedup_duplicate_of_items"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_item_dedup")),
    )
    for column in ("url_key", "text_key", "title_key", "link_key", "duplicate_of"):
        op.create_index(op.f(f"ix_item_dedup_{column}"), "item_dedup", [column], unique=False)


def downgrade() -> None:
    for column in ("url_key", "text_key", "title_key", "link_key", "duplicate_of"):
        op.drop_index(op.f(f"ix_item_dedup_{column}"), table_name="item_dedup")
    op.drop_table("item_dedup")
