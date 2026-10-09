"""Topic dossiers with hypotheses and evidence (plan 16 #4).

Revision ID: 0036
Revises: 0035
"""

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dossiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("nodes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("companies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exclude", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("statement", sa.Text(), nullable=True),
        sa.Column(
            "statement_embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True
        ),
        sa.Column("min_similarity", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_dossiers_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_dossiers_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dossiers")),
    )
    op.create_index(op.f("ix_dossiers_status"), "dossiers", ["status"], unique=False)
    op.create_table(
        "dossier_hypotheses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dossier_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_dossier_hypotheses_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dossier_id"],
            ["dossiers.id"],
            name=op.f("fk_dossier_hypotheses_dossier_id_dossiers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dossier_hypotheses")),
    )
    op.create_index(
        op.f("ix_dossier_hypotheses_dossier_id"), "dossier_hypotheses", ["dossier_id"], unique=False
    )
    op.create_table(
        "dossier_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hypothesis_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("stance", sa.String(length=10), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("added_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["added_by"],
            ["users.id"],
            name=op.f("fk_dossier_evidence_added_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["hypothesis_id"],
            ["dossier_hypotheses.id"],
            name=op.f("fk_dossier_evidence_hypothesis_id_dossier_hypotheses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_dossier_evidence_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dossier_evidence")),
        sa.UniqueConstraint("hypothesis_id", "item_id", name="uq_dossier_evidence_pair"),
    )
    op.create_index(
        op.f("ix_dossier_evidence_hypothesis_id"),
        "dossier_evidence",
        ["hypothesis_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_dossier_evidence_item_id"), "dossier_evidence", ["item_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dossier_evidence_item_id"), table_name="dossier_evidence")
    op.drop_index(op.f("ix_dossier_evidence_hypothesis_id"), table_name="dossier_evidence")
    op.drop_table("dossier_evidence")
    op.drop_index(op.f("ix_dossier_hypotheses_dossier_id"), table_name="dossier_hypotheses")
    op.drop_table("dossier_hypotheses")
    op.drop_index(op.f("ix_dossiers_status"), table_name="dossiers")
    op.drop_table("dossiers")
