"""Spotlight groups: 최근 24시간 and 지속 주목 per section, insight tags, signals and a field.

Each entry gains its `group` ("now" for the day's 24 h window, "sustained" for attention that
lasted several days), Opus's short insight `tags`, the server's deterministic `signals` and
the technology `field` of its lead card. A section's ranks are numbered per group.

Additive for readers: rows published before this revision become group "now" with no tags,
signals or field, which is what they were. Downgrading deletes the sustained rows (the old
unique rank per section cannot hold both groups).

Revision ID: 0047
Revises: 0046
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

TABLE = "spotlight_entries"
UNIQUE = "uq_spotlight_entries_rank"


def upgrade() -> None:
    op.add_column(
        TABLE, sa.Column("group", sa.String(length=20), nullable=False, server_default="now")
    )
    op.add_column(
        TABLE,
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "signals",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(TABLE, sa.Column("field", sa.String(length=40), nullable=True))
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.create_unique_constraint(UNIQUE, TABLE, ["spotlight_id", "section", "group", "rank"])


def downgrade() -> None:
    op.execute(sa.text(f"DELETE FROM {TABLE} WHERE \"group\" <> 'now'"))
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.create_unique_constraint(UNIQUE, TABLE, ["spotlight_id", "section", "rank"])
    op.drop_column(TABLE, "field")
    op.drop_column(TABLE, "signals")
    op.drop_column(TABLE, "tags")
    op.drop_column(TABLE, "group")
