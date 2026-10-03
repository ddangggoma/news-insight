"""Korean item cards (Antigravity CLI primary, local Qwen fallback) and card runs.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("batches", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quota", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card_runs")),
    )
    op.create_index(op.f("ix_card_runs_started_at"), "card_runs", ["started_at"], unique=False)
    op.create_table(
        "item_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ready", "failed", name="cardstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("title_ko", sa.Text(), nullable=True),
        sa.Column("summary_ko", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("engine", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_item_cards_item_id_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_cards")),
        sa.UniqueConstraint("item_id", name=op.f("uq_item_cards_item_id")),
    )
    op.create_index("ix_item_cards_generated_at", "item_cards", ["generated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_item_cards_generated_at", table_name="item_cards")
    op.drop_table("item_cards")
    op.drop_index(op.f("ix_card_runs_started_at"), table_name="card_runs")
    op.drop_table("card_runs")
