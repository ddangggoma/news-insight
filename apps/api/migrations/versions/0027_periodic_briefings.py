"""Weekly and monthly briefings built from the period's daily briefings (plan 13 C4).

Revision ID: 0027
Revises: 0026
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "periodic_briefings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("period_key", sa.String(length=10), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_periodic_briefings")),
        sa.UniqueConstraint("kind", "period_key", "version", name="uq_periodic_briefings_version"),
    )
    op.create_index(op.f("ix_periodic_briefings_period_key"), "periodic_briefings", ["period_key"])


def downgrade() -> None:
    op.drop_index(op.f("ix_periodic_briefings_period_key"), table_name="periodic_briefings")
    op.drop_table("periodic_briefings")
