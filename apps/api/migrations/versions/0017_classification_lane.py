"""Classification-only lane and out-of-taxonomy topic candidates (checklist CLS-1, CLS-2).

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "item_cards",
        sa.Column("classify_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "item_cards",
        sa.Column(
            "topic_candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "card_runs", sa.Column("classified", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("card_runs", "classified")
    op.drop_column("item_cards", "topic_candidates")
    op.drop_column("item_cards", "classify_attempts")
