"""Daily briefing freezes and immutable briefing versions with gate results (P6).

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "briefing_freezes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("briefing_date", sa.Date(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidate_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("taxonomy_revision", sa.String(length=20), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_briefing_freezes")),
        sa.UniqueConstraint("briefing_date", name=op.f("uq_briefing_freezes_briefing_date")),
    )
    op.create_table(
        "briefings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("briefing_date", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("published", "blocked", name="briefingstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("freeze_id", sa.Integer(), nullable=False),
        sa.Column("digest_id", sa.Integer(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("shortlist", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["digest_id"], ["digests.id"], name=op.f("fk_briefings_digest_id_digests")
        ),
        sa.ForeignKeyConstraint(
            ["freeze_id"],
            ["briefing_freezes.id"],
            name=op.f("fk_briefings_freeze_id_briefing_freezes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_briefings")),
        sa.UniqueConstraint("briefing_date", "version", name="uq_briefings_date_version"),
    )
    op.create_index(
        op.f("ix_briefings_briefing_date"), "briefings", ["briefing_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_briefings_briefing_date"), table_name="briefings")
    op.drop_table("briefings")
    op.drop_table("briefing_freezes")
