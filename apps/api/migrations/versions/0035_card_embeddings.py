"""Card embeddings for questions over the corpus (plan 16 #1).

bge-m3 over each ready card's Korean title and summary. No ANN index, as with item_embeddings
(0033): an exact scan answers a question in seconds.

Revision ID: 0035
Revises: 0034
"""

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_embeddings",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_card_embeddings_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_card_embeddings")),
    )
    op.create_index(
        op.f("ix_card_embeddings_created_at"), "card_embeddings", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_card_embeddings_created_at"), table_name="card_embeddings")
    op.drop_table("card_embeddings")
