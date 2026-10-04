"""Strategy runs (30 personas, Writer report, Reviewer verdict) linked to briefings (P7).

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("briefing_date", sa.Date(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ok", "failed", name="strategystatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("personas", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("review", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dropped_claims", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_runs")),
    )
    op.create_index(
        op.f("ix_strategy_runs_briefing_date"), "strategy_runs", ["briefing_date"], unique=False
    )
    op.create_index(
        op.f("ix_strategy_runs_input_hash"), "strategy_runs", ["input_hash"], unique=False
    )
    op.add_column("briefings", sa.Column("strategy_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_briefings_strategy_id_strategy_runs"),
        "briefings",
        "strategy_runs",
        ["strategy_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_briefings_strategy_id_strategy_runs"), "briefings", type_="foreignkey"
    )
    op.drop_column("briefings", "strategy_id")
    op.drop_index(op.f("ix_strategy_runs_input_hash"), table_name="strategy_runs")
    op.drop_index(op.f("ix_strategy_runs_briefing_date"), table_name="strategy_runs")
    op.drop_table("strategy_runs")
