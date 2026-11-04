"""Spotlight: the day's frozen candidates, the Opus-written Top 10s and their entries (plan 18).

Additive: three new tables. Code from before this revision never reads them.

Revision ID: 0044
Revises: 0043
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spotlight_freezes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("spotlight_date", sa.Date(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spotlight_freezes")),
        sa.UniqueConstraint("spotlight_date", name=op.f("uq_spotlight_freezes_spotlight_date")),
    )
    op.create_table(
        "spotlights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("spotlight_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("published", "failed", name="spotlightstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("benchmark_note", sa.Text(), nullable=False),
        sa.Column("freeze_id", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["freeze_id"],
            ["spotlight_freezes.id"],
            name=op.f("fk_spotlights_freeze_id_spotlight_freezes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spotlights")),
        sa.UniqueConstraint("spotlight_date", name=op.f("uq_spotlights_spotlight_date")),
    )
    op.create_table(
        "spotlight_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("spotlight_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("stat_rank", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("item_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("title_ko", sa.Text(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("why_hot", sa.Text(), nullable=False),
        sa.Column("rank_note", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["spotlight_id"],
            ["spotlights.id"],
            name=op.f("fk_spotlight_entries_spotlight_id_spotlights"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spotlight_entries")),
        sa.UniqueConstraint("spotlight_id", "section", "rank", name="uq_spotlight_entries_rank"),
    )


def downgrade() -> None:
    op.drop_table("spotlight_entries")
    op.drop_table("spotlights")
    op.drop_table("spotlight_freezes")
