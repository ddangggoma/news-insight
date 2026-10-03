"""Item metric snapshots (engagement signals over time).

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_metric_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name="fk_item_metric_snapshots_item_id_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_item_metric_snapshots"),
    )
    op.create_index(
        "ix_item_metric_snapshots_item_captured",
        "item_metric_snapshots",
        ["item_id", "captured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_item_metric_snapshots_item_captured", table_name="item_metric_snapshots")
    op.drop_table("item_metric_snapshots")
