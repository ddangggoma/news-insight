"""Time-window and theme indexes (checklist PERF-1).

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_items_first_seen_at", "items", ["first_seen_at"])
    op.create_index("ix_items_source_first_seen", "items", ["source_id", "first_seen_at"])
    op.create_index(
        "ix_items_body_expires_at",
        "items",
        ["body_expires_at"],
        postgresql_where=sa.text("body_expires_at IS NOT NULL"),
    )
    op.create_index("ix_item_cards_themes", "item_cards", ["themes"], postgresql_using="gin")
    op.create_index(
        "ix_item_metric_snapshots_captured_at", "item_metric_snapshots", ["captured_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_item_metric_snapshots_captured_at", table_name="item_metric_snapshots")
    op.drop_index("ix_item_cards_themes", table_name="item_cards")
    op.drop_index("ix_items_body_expires_at", table_name="items")
    op.drop_index("ix_items_source_first_seen", table_name="items")
    op.drop_index("ix_items_first_seen_at", table_name="items")
