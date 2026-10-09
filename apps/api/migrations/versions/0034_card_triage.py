"""Carding priority before the LLM: title-embedding DX model and per-item scores (plan 16 #3).

Revision ID: 0034
Revises: 0033
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "triage_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=False),
        sa.Column("auc", sa.Float(), nullable=False),
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("centroids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_triage_models")),
    )
    op.create_table(
        "item_triage",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("dx_probability", sa.Float(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("themes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("matched", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_item_triage_item_id_items"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["triage_models.id"],
            name=op.f("fk_item_triage_model_id_triage_models"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_item_triage")),
    )
    op.create_index(op.f("ix_item_triage_score"), "item_triage", ["score"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_item_triage_score"), table_name="item_triage")
    op.drop_table("item_triage")
    op.drop_table("triage_models")
