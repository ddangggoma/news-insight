"""Daily radar signal snapshots (checklist PRD-1).

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "radar_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("window_key", sa.String(length=20), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("tone", sa.String(length=10), nullable=False),
        sa.Column("focus_kind", sa.String(length=10), nullable=False),
        sa.Column("focus_key", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radar_signals")),
        sa.UniqueConstraint(
            "snapshot_date", "period", "window_key", "tone", name="uq_radar_signals"
        ),
    )
    op.create_index(op.f("ix_radar_signals_snapshot_date"), "radar_signals", ["snapshot_date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_radar_signals_snapshot_date"), table_name="radar_signals")
    op.drop_table("radar_signals")
