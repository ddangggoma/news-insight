"""Community buzz clusters and breaking signals (2026-11-19 signal layer).

`buzz_item_keys`: what each community post is matched by (links, references, title MinHash),
computed once. `buzz_clusters`: posts about one thing, their counts, threshold, breaking, push
and one Korean summary. `buzz_cluster_items`: a post's cluster.

Additive: three new tables. Code from before this revision never reads them. PR #155 uses 0051;
whichever merges second points `down_revision` at the other (memory: parallel migration numbers).

Revision ID: 0052
Revises: 0050
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0052"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "buzz_clusters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("post_count", sa.Integer(), nullable=False),
        sa.Column("human_posts", sa.Integer(), nullable=False),
        sa.Column("author_count", sa.Integer(), nullable=False),
        sa.Column("platform_count", sa.Integer(), nullable=False),
        sa.Column("platforms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("heat", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("lead_item_id", sa.Integer(), nullable=True),
        sa.Column("crossed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("breaking", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("breaking_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("news_item_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("news_first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("news_caught_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title_ko", sa.Text(), nullable=True),
        sa.Column("summary_ko", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_event", sa.Boolean(), nullable=True),
        sa.Column("relevant", sa.Boolean(), nullable=True),
        sa.Column("summary_engine", sa.String(length=20), nullable=True),
        sa.Column("summary_model", sa.String(length=80), nullable=True),
        sa.Column("summarized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_posts", sa.Integer(), nullable=False),
        sa.Column("summary_count", sa.Integer(), nullable=False),
        sa.Column("summary_attempts", sa.Integer(), nullable=False),
        sa.Column("summary_tried_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_error", sa.Text(), nullable=True),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("push_channels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("merged_into", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["lead_item_id"],
            ["items.id"],
            name=op.f("fk_buzz_clusters_lead_item_id_items"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["merged_into"],
            ["buzz_clusters.id"],
            name=op.f("fk_buzz_clusters_merged_into_buzz_clusters"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_buzz_clusters")),
    )
    op.create_index(
        "ix_buzz_clusters_crossed_at",
        "buzz_clusters",
        ["crossed_at"],
        unique=False,
        postgresql_where=sa.text("crossed_at IS NOT NULL"),
    )
    op.create_index(
        "ix_buzz_clusters_last_seen_at", "buzz_clusters", ["last_seen_at"], unique=False
    )
    op.create_table(
        "buzz_item_keys",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("author", sa.String(length=340), nullable=True),
        sa.Column("links", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("signature", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("bands", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("words", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_buzz_item_keys_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_buzz_item_keys")),
    )
    op.create_index(
        "ix_buzz_item_keys_first_seen_at", "buzz_item_keys", ["first_seen_at"], unique=False
    )
    op.create_table(
        "buzz_cluster_items",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("cluster_id", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["buzz_clusters.id"],
            name=op.f("fk_buzz_cluster_items_cluster_id_buzz_clusters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_buzz_cluster_items_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_buzz_cluster_items")),
    )
    op.create_index(
        op.f("ix_buzz_cluster_items_cluster_id"), "buzz_cluster_items", ["cluster_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_buzz_cluster_items_cluster_id"), table_name="buzz_cluster_items")
    op.drop_table("buzz_cluster_items")
    op.drop_index("ix_buzz_item_keys_first_seen_at", table_name="buzz_item_keys")
    op.drop_table("buzz_item_keys")
    op.drop_index("ix_buzz_clusters_last_seen_at", table_name="buzz_clusters")
    op.drop_index(
        "ix_buzz_clusters_crossed_at",
        table_name="buzz_clusters",
        postgresql_where=sa.text("crossed_at IS NOT NULL"),
    )
    op.drop_table("buzz_clusters")
