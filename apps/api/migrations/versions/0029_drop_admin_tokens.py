"""Drop the magic-link tokens: site accounts with passwords replace them (plan 14).

Revision ID: 0029
Revises: 0028
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f("ix_admin_tokens_created_at"), table_name="admin_tokens")
    op.drop_table("admin_tokens")


def downgrade() -> None:
    op.create_table(
        "admin_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("login", "session", name="tokenkind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_admin_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_admin_tokens_created_at"), "admin_tokens", ["created_at"], unique=False
    )
