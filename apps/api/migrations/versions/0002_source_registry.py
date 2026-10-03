"""Source registry and validation ladder audit trail.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("track", sa.String(32), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("access_method", sa.String(32), nullable=False),
        sa.Column("endpoint_url", sa.String(2048), nullable=False),
        sa.Column("official_domain", sa.String(253), nullable=False),
        sa.Column("operator", sa.String(200), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("poll_class", sa.String(32), nullable=False),
        sa.Column("dx_relevance", sa.Text(), nullable=False),
        sa.Column("terms_url", sa.String(2048), nullable=True),
        sa.Column("storage_right", sa.String(32), nullable=True),
        sa.Column("validation_stage", sa.String(32), server_default="unverified", nullable=False),
        sa.Column("status", sa.String(32), server_default="candidate", nullable=False),
        sa.Column("paused_reason", sa.Text(), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("key", name="uq_sources_key"),
    )
    op.create_index("ix_sources_track", "sources", ["track"])
    op.create_index("ix_sources_status_stage", "sources", ["status", "validation_stage"])

    op.create_table(
        "source_validation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_source_validation_events_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_validation_events"),
    )
    op.create_index(
        "ix_source_validation_events_source_id", "source_validation_events", ["source_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_validation_events_source_id", table_name="source_validation_events")
    op.drop_table("source_validation_events")
    op.drop_index("ix_sources_status_stage", table_name="sources")
    op.drop_index("ix_sources_track", table_name="sources")
    op.drop_table("sources")
