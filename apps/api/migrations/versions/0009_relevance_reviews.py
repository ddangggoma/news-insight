"""Operator relevance reviews (random-sample labels; P4 evaluation set).

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relevance_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column(
            "verdict",
            sa.Enum(
                "relevant", "irrelevant", "unsure", name="verdict", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sample_seed", sa.String(length=40), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_relevance_reviews_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_relevance_reviews")),
        sa.UniqueConstraint("item_id", name=op.f("uq_relevance_reviews_item_id")),
    )
    op.create_index(
        op.f("ix_relevance_reviews_reviewed_at"), "relevance_reviews", ["reviewed_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_relevance_reviews_reviewed_at"), table_name="relevance_reviews")
    op.drop_table("relevance_reviews")
