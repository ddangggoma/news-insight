"""Article date index: trends and lists bucket items by coalesce(published_at, first_seen_at).

Additive: one expression index, built concurrently so collection keeps writing. Code from
before this revision never reads it.

Revision ID: 0043
Revises: 0042
"""

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_items_occurred_at"
            " ON items (coalesce(published_at, first_seen_at))"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_items_occurred_at")
