"""Signal type on cards (taxonomy v2, plan 09 §3-2).

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_cards", sa.Column("signal_type", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_item_cards_signal_type"), "item_cards", ["signal_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_item_cards_signal_type"), table_name="item_cards")
    op.drop_column("item_cards", "signal_type")
