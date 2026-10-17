"""Access log: pages, actions and route calls of signed-in accounts, kept 30 days.

Additive: a new table only. Code from before this revision never touches it.

Revision ID: 0041
Revises: 0040
"""

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "page",
                "action",
                "api",
                "media",
                name="accesskind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_access_logs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_logs")),
    )
    op.create_index(op.f("ix_access_logs_at"), "access_logs", ["at"])
    op.create_index("ix_access_logs_user_id_at", "access_logs", ["user_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_access_logs_user_id_at", table_name="access_logs")
    op.drop_index(op.f("ix_access_logs_at"), table_name="access_logs")
    op.drop_table("access_logs")
