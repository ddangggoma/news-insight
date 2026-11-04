"""Daily Opus insights of the 연구 and 특허 menus (plan 19 §3, P4).

`domain_insights`: one row per date and kind (research, patent) with the writer's status, model,
cost and the validated payload (overview sentences, field and company one-liners, the watched-
company line). A published row is never rewritten; a failed one is overwritten by the next try.

Additive: one new table. Code from before this revision never reads it.

Revision ID: 0050
Revises: 0049
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def _status(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


def upgrade() -> None:
    op.create_table(
        "domain_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("insight_date", sa.Date(), nullable=False),
        sa.Column("kind", _status("research", "patent", name="insightkind"), nullable=False),
        sa.Column("status", _status("published", "failed", name="insightstatus"), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_domain_insights")),
        sa.UniqueConstraint("insight_date", "kind", name="uq_domain_insights_date_kind"),
    )


def downgrade() -> None:
    op.drop_table("domain_insights")
