"""Index items.content_hash for the exact-duplicate lookup in story clustering (2026-10-05).

Revision ID: 0022
Revises: 0021
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(op.f("ix_items_content_hash"), "items", ["content_hash"])


def downgrade() -> None:
    op.drop_index(op.f("ix_items_content_hash"), table_name="items")
