"""Spotlight news insight: a 시사점 per news entry and the day's overview (plan 20).

`spotlight_entries.insight` is what a news entry means for the DX businesses (one sentence by
the writer). `spotlights.news_overview` holds the day's themes and the reader's interest areas,
each pointing at news entries of that day by key. Both are nullable: days published before this
revision have neither and are shown as they were.

Revision ID: 0051
Revises: 0050
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("spotlight_entries", sa.Column("insight", sa.Text(), nullable=True))
    op.add_column(
        "spotlights",
        sa.Column("news_overview", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("spotlights", "news_overview")
    op.drop_column("spotlight_entries", "insight")
