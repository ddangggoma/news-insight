"""Title embeddings and judged pairs for multilingual story merging (checklist CLU-1).

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_embeddings",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("vector", postgresql.ARRAY(postgresql.REAL()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_item_embeddings_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_item_embeddings")),
    )
    op.create_index(op.f("ix_item_embeddings_created_at"), "item_embeddings", ["created_at"])
    op.create_table(
        "story_merge_checks",
        sa.Column("item_a", sa.Integer(), nullable=False),
        sa.Column("item_b", sa.Integer(), nullable=False),
        sa.Column("cosine", sa.Float(), nullable=False),
        sa.Column("same", sa.Boolean(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_a"],
            ["items.id"],
            name=op.f("fk_story_merge_checks_item_a_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_b"],
            ["items.id"],
            name=op.f("fk_story_merge_checks_item_b_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_a", "item_b", name=op.f("pk_story_merge_checks")),
    )


def downgrade() -> None:
    op.drop_table("story_merge_checks")
    op.drop_index(op.f("ix_item_embeddings_created_at"), table_name="item_embeddings")
    op.drop_table("item_embeddings")
