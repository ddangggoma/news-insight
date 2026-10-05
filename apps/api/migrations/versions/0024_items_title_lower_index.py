"""Index lower(items.title) for the same-headline lookup in story clustering (2026-10-05).

Revision ID: 0024
Revises: 0023
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_items_title_lower ON items (lower(title))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_items_title_lower")
