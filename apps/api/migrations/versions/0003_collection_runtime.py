"""Collection runtime: scheduling state, fetch runs, dead letters.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _counter(name: str) -> sa.Column[int]:
    return sa.Column(name, sa.Integer(), server_default="0", nullable=False)


def upgrade() -> None:
    op.create_table(
        "source_runtimes",
        sa.Column("source_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        _counter("consecutive_failures"),
        _counter("consecutive_idle"),
        sa.Column("etag", sa.String(500), nullable=True),
        sa.Column("last_modified", sa.String(200), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_source_runtimes_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("source_id", name="pk_source_runtimes"),
    )
    op.create_index("ix_source_runtimes_next_due_at", "source_runtimes", ["next_due_at"])

    op.create_table(
        "fetch_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("canary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        _counter("items_seen"),
        _counter("items_new"),
        _counter("items_updated"),
        _counter("items_unchanged"),
        _counter("items_incomplete"),
        _counter("duplicate_urls"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_fetch_runs_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fetch_runs"),
    )
    op.create_index("ix_fetch_runs_source_started", "fetch_runs", ["source_id", "started_at"])

    op.create_table(
        "dead_letters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_dead_letters_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fetch_run_id"],
            ["fetch_runs.id"],
            name="fk_dead_letters_fetch_run_id_fetch_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dead_letters"),
    )
    op.create_index("ix_dead_letters_source_id", "dead_letters", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_dead_letters_source_id", table_name="dead_letters")
    op.drop_table("dead_letters")
    op.drop_index("ix_fetch_runs_source_started", table_name="fetch_runs")
    op.drop_table("fetch_runs")
    op.drop_index("ix_source_runtimes_next_due_at", table_name="source_runtimes")
    op.drop_table("source_runtimes")
