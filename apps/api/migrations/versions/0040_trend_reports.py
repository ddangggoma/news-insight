"""Trend reports on a reader's topic, written on the host with the Claude CLI (plan 17 R1).

Revision ID: 0040
Revises: 0039
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trend_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("brief", sa.Text(), nullable=True),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("dossier_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["dossier_id"],
            ["dossiers.id"],
            name=op.f("fk_trend_reports_dossier_id_dossiers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_trend_reports_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trend_reports")),
    )
    op.create_index(op.f("ix_trend_reports_status"), "trend_reports", ["status"])
    op.create_index(op.f("ix_trend_reports_requested_at"), "trend_reports", ["requested_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_trend_reports_requested_at"), table_name="trend_reports")
    op.drop_index(op.f("ix_trend_reports_status"), table_name="trend_reports")
    op.drop_table("trend_reports")
