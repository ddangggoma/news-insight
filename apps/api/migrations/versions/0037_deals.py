"""Deals from the cards: investments, acquisitions, partnerships (plan 16 #8).

Revision ID: 0037
Revises: 0036
"""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deal_scans",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("found", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_deal_scans_item_id_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_deal_scans")),
    )
    op.create_table(
        "deals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=160), nullable=False),
        sa.Column("actor_key", sa.String(length=80), nullable=True),
        sa.Column("counterparty", sa.String(length=160), nullable=True),
        sa.Column("counterparty_key", sa.String(length=80), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("amount_usd", sa.Float(), nullable=True),
        sa.Column("stage", sa.String(length=40), nullable=True),
        sa.Column("announced_on", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"], ["items.id"], name=op.f("fk_deals_item_id_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deals")),
    )
    op.create_index(op.f("ix_deals_actor_key"), "deals", ["actor_key"], unique=False)
    op.create_index(op.f("ix_deals_announced_on"), "deals", ["announced_on"], unique=False)
    op.create_index(op.f("ix_deals_counterparty_key"), "deals", ["counterparty_key"], unique=False)
    op.create_index(op.f("ix_deals_item_id"), "deals", ["item_id"], unique=False)
    op.create_index(op.f("ix_deals_kind"), "deals", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_deals_kind"), table_name="deals")
    op.drop_index(op.f("ix_deals_item_id"), table_name="deals")
    op.drop_index(op.f("ix_deals_counterparty_key"), table_name="deals")
    op.drop_index(op.f("ix_deals_announced_on"), table_name="deals")
    op.drop_index(op.f("ix_deals_actor_key"), table_name="deals")
    op.drop_table("deals")
    op.drop_table("deal_scans")
