"""Team collaboration: comments (card memos), shared collections (plan 16 #12).

Revision ID: 0038
Revises: 0037
"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_collections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_team_collections_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_collections")),
    )
    op.create_index(
        op.f("ix_team_collections_status"), "team_collections", ["status"], unique=False
    )
    op.create_table(
        "team_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_kind", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_team_comments_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_comments")),
    )
    op.create_index(
        "ix_team_comments_target", "team_comments", ["target_kind", "target_id"], unique=False
    )
    op.create_table(
        "team_collection_items",
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("added_by", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["added_by"],
            ["users.id"],
            name=op.f("fk_team_collection_items_added_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["team_collections.id"],
            name=op.f("fk_team_collection_items_collection_id_team_collections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_team_collection_items_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("collection_id", "item_id", name=op.f("pk_team_collection_items")),
    )
    op.create_index(
        op.f("ix_team_collection_items_item_id"), "team_collection_items", ["item_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_team_collection_items_item_id"), table_name="team_collection_items")
    op.drop_table("team_collection_items")
    op.drop_index("ix_team_comments_target", table_name="team_comments")
    op.drop_table("team_comments")
    op.drop_index(op.f("ix_team_collections_status"), table_name="team_collections")
    op.drop_table("team_collections")
