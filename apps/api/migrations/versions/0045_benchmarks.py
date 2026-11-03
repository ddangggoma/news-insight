"""Benchmarks: leaderboard snapshots, per-model scores and the AI model registry (plan 18).

Additive: four new tables. Code from before this revision never reads them.

Revision ID: 0045
Revises: 0044
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("org", sa.String(length=80), nullable=True),
        sa.Column("open_weights", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_models")),
        sa.UniqueConstraint("name", name=op.f("uq_ai_models_name")),
    )
    op.create_table(
        "ai_model_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["ai_models.id"],
            name=op.f("fk_ai_model_aliases_model_id_ai_models"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_model_aliases")),
        sa.UniqueConstraint("alias", name=op.f("uq_ai_model_aliases_alias")),
    )
    op.create_index(
        op.f("ix_ai_model_aliases_model_id"), "ai_model_aliases", ["model_id"], unique=False
    )
    op.create_table(
        "benchmark_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site", sa.String(length=40), nullable=False),
        sa.Column("release", sa.String(length=40), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_benchmark_snapshots")),
        sa.UniqueConstraint("site", "sha256", name="uq_benchmark_snapshots_site_sha"),
    )
    op.create_table(
        "benchmark_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("site", sa.String(length=40), nullable=False),
        sa.Column("board", sa.String(length=60), nullable=False),
        sa.Column("model_raw", sa.String(length=200), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("org", sa.String(length=80), nullable=True),
        sa.Column("config", sa.String(length=120), nullable=True),
        sa.Column("metric", sa.String(length=60), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("ci_low", sa.Float(), nullable=True),
        sa.Column("ci_high", sa.Float(), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_id"], ["ai_models.id"], name=op.f("fk_benchmark_scores_model_id_ai_models")
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["benchmark_snapshots.id"],
            name=op.f("fk_benchmark_scores_snapshot_id_benchmark_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_benchmark_scores")),
    )
    op.create_index(
        op.f("ix_benchmark_scores_snapshot_id"), "benchmark_scores", ["snapshot_id"], unique=False
    )
    op.create_index(
        op.f("ix_benchmark_scores_model_id"), "benchmark_scores", ["model_id"], unique=False
    )


def downgrade() -> None:
    op.drop_table("benchmark_scores")
    op.drop_table("benchmark_snapshots")
    op.drop_table("ai_model_aliases")
    op.drop_table("ai_models")
