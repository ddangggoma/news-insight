"""Operational alert episodes (P9 monitoring).

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("critical", "warning", "info", name="severity", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ops_alerts")),
    )
    op.create_index("ix_ops_alerts_open", "ops_alerts", ["key", "resolved_at"], unique=False)
    op.create_index(op.f("ix_ops_alerts_opened_at"), "ops_alerts", ["opened_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ops_alerts_opened_at"), table_name="ops_alerts")
    op.drop_index("ix_ops_alerts_open", table_name="ops_alerts")
    op.drop_table("ops_alerts")
