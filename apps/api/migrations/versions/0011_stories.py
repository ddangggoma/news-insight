"""Stories: MinHash signatures, LSH bands, issue clusters and cross-track identifiers (P4).

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_lsh",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("band", sa.SmallInteger(), nullable=False),
        sa.Column("hash", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_item_lsh_item_id_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("item_id", "band", name=op.f("pk_item_lsh")),
    )
    op.create_index("ix_item_lsh_band_hash", "item_lsh", ["band", "hash"], unique=False)
    op.create_table(
        "item_refs",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("value", sa.String(length=300), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_item_refs_item_id_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("item_id", "kind", "value", name=op.f("pk_item_refs")),
    )
    op.create_index("ix_item_refs_kind_value", "item_refs", ["kind", "value"], unique=False)
    op.create_table(
        "item_signatures",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("dedup_key", sa.String(length=2048), nullable=False),
        sa.Column("signature", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_item_signatures_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_item_signatures")),
    )
    op.create_index(
        op.f("ix_item_signatures_dedup_key"), "item_signatures", ["dedup_key"], unique=False
    )
    op.create_table(
        "stories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("representative_item_id", sa.Integer(), nullable=False),
        sa.Column("title_ko", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("tracks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("max_relevance", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["representative_item_id"],
            ["items.id"],
            name=op.f("fk_stories_representative_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stories")),
    )
    op.create_index(op.f("ix_stories_last_seen_at"), "stories", ["last_seen_at"], unique=False)
    op.create_index(
        op.f("ix_stories_representative_item_id"),
        "stories",
        ["representative_item_id"],
        unique=False,
    )
    op.create_table(
        "story_items",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column(
            "relation",
            sa.Enum(
                "seed", "exact", "near", "event", name="relation", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_story_items_item_id_items"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["stories.id"],
            name=op.f("fk_story_items_story_id_stories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_story_items")),
    )
    op.create_index(op.f("ix_story_items_story_id"), "story_items", ["story_id"], unique=False)

    op.create_index("ix_item_cards_keywords", "item_cards", ["keywords"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_item_cards_keywords", table_name="item_cards")
    op.drop_index(op.f("ix_story_items_story_id"), table_name="story_items")
    op.drop_table("story_items")
    op.drop_index(op.f("ix_stories_representative_item_id"), table_name="stories")
    op.drop_index(op.f("ix_stories_last_seen_at"), table_name="stories")
    op.drop_table("stories")
    op.drop_index(op.f("ix_item_signatures_dedup_key"), table_name="item_signatures")
    op.drop_table("item_signatures")
    op.drop_index("ix_item_refs_kind_value", table_name="item_refs")
    op.drop_table("item_refs")
    op.drop_index("ix_item_lsh_band_hash", table_name="item_lsh")
    op.drop_table("item_lsh")
