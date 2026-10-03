"""Items and append-only item revisions (seen ledger).

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("track", sa.String(32), nullable=False),
        sa.Column("stable_id", sa.String(500), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("body_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author", sa.String(300), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("canary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_items_source_id_sources", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_items"),
        sa.UniqueConstraint("source_id", "stable_id", name="uq_items_source_stable"),
    )
    op.create_index("ix_items_canonical_url", "items", ["canonical_url"])
    op.create_index("ix_items_published_at", "items", ["published_at"])

    op.create_table(
        "item_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name="fk_item_revisions_item_id_items", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["fetch_run_id"],
            ["fetch_runs.id"],
            name="fk_item_revisions_fetch_run_id_fetch_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_item_revisions"),
        sa.UniqueConstraint("item_id", "revision", name="uq_item_revisions_item_revision"),
    )
    op.create_index("ix_item_revisions_item_id", "item_revisions", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_item_revisions_item_id", table_name="item_revisions")
    op.drop_table("item_revisions")
    op.drop_index("ix_items_published_at", table_name="items")
    op.drop_index("ix_items_canonical_url", table_name="items")
    op.drop_table("items")
