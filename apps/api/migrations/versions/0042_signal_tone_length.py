"""Radar signal tone up to 20 characters: company tones ("company_shift", 13) overflowed
varchar(10) and rolled back the briefing freeze of 2026-10-26 and 10-27.

Widening a varchar is a catalog-only change in Postgres; code from before this revision
writes shorter values and keeps working.

Revision ID: 0042
Revises: 0041
"""

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "radar_signals",
        "tone",
        existing_type=sa.String(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "radar_signals",
        "tone",
        existing_type=sa.String(length=20),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
