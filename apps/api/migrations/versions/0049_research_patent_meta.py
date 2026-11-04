"""Research and patent metadata, and their daily counts (plan 19 P1).

`research_meta`: OpenAlex venue, topic, institutions (linked to registry companies) and
citations per paper. `patent_meta`: publication number, office, CPC/IPC codes, applicants,
company keys and technology field per patent document or patent news item.
`research_daily_stats` and `patent_daily_stats`: documents per KST day by field, theme,
company, organisation, country and office, rebuilt daily for the 연구 and 특허 menus;
`stats_days` marks the days built (the reader's as_of) with their enrichment coverage;
`research_signals`: per recent paper, what the 주목 문헌 list filters and ranks by.

Additive: six new tables. Code from before this revision never reads them.

Revision ID: 0049
Revises: 0048
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

EMPTY_ARRAY = sa.text("'{}'")


def _status(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


def upgrade() -> None:
    op.create_table(
        "research_meta",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("doi", sa.String(length=300), nullable=True),
        sa.Column("openalex_id", sa.String(length=40), nullable=True),
        sa.Column("venue", sa.String(length=300), nullable=True),
        sa.Column("oa_field", sa.String(length=120), nullable=True),
        sa.Column("oa_subfield", sa.String(length=120), nullable=True),
        sa.Column("oa_topic", sa.String(length=300), nullable=True),
        sa.Column(
            "institutions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "countries",
            postgresql.ARRAY(sa.String(length=2)),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column("has_company", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "company_keys",
            postgresql.ARRAY(sa.String(length=80)),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column("cited_by", sa.Integer(), nullable=True),
        sa.Column("fwci", sa.Float(), nullable=True),
        sa.Column(
            "counts_by_year",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status", _status("ok", "not_found", "error", name="enrichstatus"), nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_research_meta_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_research_meta")),
    )
    op.create_index(
        "ix_research_meta_company_keys",
        "research_meta",
        ["company_keys"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index("ix_research_meta_doi", "research_meta", ["doi"], unique=False)
    op.create_index(
        "ix_research_meta_status_enriched_at",
        "research_meta",
        ["status", "enriched_at"],
        unique=False,
    )
    op.create_table(
        "patent_meta",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("publication_number", sa.String(length=40), nullable=True),
        sa.Column("kind", sa.String(length=4), nullable=True),
        sa.Column("office", sa.String(length=4), nullable=True),
        sa.Column("priority_date", sa.Date(), nullable=True),
        sa.Column(
            "cpc", postgresql.ARRAY(sa.String(length=40)), server_default="{}", nullable=False
        ),
        sa.Column(
            "ipc", postgresql.ARRAY(sa.String(length=40)), server_default="{}", nullable=False
        ),
        sa.Column(
            "applicants",
            postgresql.ARRAY(sa.String(length=300)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "company_keys",
            postgresql.ARRAY(sa.String(length=80)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("field", sa.String(length=40), nullable=False),
        sa.Column(
            "fields", postgresql.ARRAY(sa.String(length=40)), server_default="{}", nullable=False
        ),
        sa.Column("source", _status("ops", "eps", "news", name="patentsource"), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_patent_meta_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_patent_meta")),
    )
    op.create_index(
        "ix_patent_meta_company_keys",
        "patent_meta",
        ["company_keys"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index("ix_patent_meta_field", "patent_meta", ["field"], unique=False)
    op.create_table(
        "research_daily_stats",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("dim", sa.String(length=10), nullable=False),
        sa.Column("field", sa.String(length=40), nullable=False),
        sa.Column("theme", sa.String(length=80), nullable=False),
        sa.Column("company_key", sa.String(length=80), nullable=False),
        sa.Column("org_name", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("org_type", sa.String(length=20), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("n_company", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "day",
            "dim",
            "field",
            "theme",
            "company_key",
            "org_name",
            "country",
            name=op.f("pk_research_daily_stats"),
        ),
    )
    op.create_index(
        "ix_research_daily_stats_dim_day", "research_daily_stats", ["dim", "day"], unique=False
    )
    op.create_index(
        "ix_research_daily_stats_dim_org_day",
        "research_daily_stats",
        ["dim", "org_name", "day"],
        unique=False,
    )
    op.create_table(
        "patent_daily_stats",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("dim", sa.String(length=10), nullable=False),
        sa.Column("field", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("company_key", sa.String(length=80), nullable=False),
        sa.Column("office", sa.String(length=4), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "day",
            "dim",
            "field",
            "source",
            "company_key",
            "office",
            name=op.f("pk_patent_daily_stats"),
        ),
    )
    op.create_index(
        "ix_patent_daily_stats_dim_day", "patent_daily_stats", ["dim", "day"], unique=False
    )
    op.create_table(
        "stats_days",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_docs", sa.Integer(), nullable=False),
        sa.Column("research_enriched", sa.Integer(), nullable=False),
        sa.Column("patent_docs", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_stats_days")),
    )
    op.create_table(
        "research_signals",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("field", sa.String(length=40), nullable=False),
        sa.Column(
            "company_keys",
            postgresql.ARRAY(sa.String(length=80)),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column(
            "orgs",
            postgresql.ARRAY(sa.String(length=200)),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column("canon_key", sa.String(length=320), nullable=True),
        sa.Column("lead", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("mentions", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("upvotes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cited_growth", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("score", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_research_signals_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_research_signals")),
    )
    op.create_index(
        "ix_research_signals_lead_day",
        "research_signals",
        ["day"],
        unique=False,
        postgresql_where=sa.text("lead"),
    )
    op.create_index(
        "ix_research_signals_company_keys",
        "research_signals",
        ["company_keys"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_research_signals_orgs",
        "research_signals",
        ["orgs"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("research_signals")
    op.drop_table("stats_days")
    op.drop_table("patent_daily_stats")
    op.drop_table("research_daily_stats")
    op.drop_table("patent_meta")
    op.drop_table("research_meta")
