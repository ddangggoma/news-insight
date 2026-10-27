"""Technology keys leave out bare versions, CVE/EUVD ids and CVSS scores.

EUVD/CVE bot toots put "CVSS v3.1" and "v3.1" into card keywords, so ~18k cards carried
keys like `v3.1`, `cvssv3.1` and `cve2026109618` into the word cloud, 국내 공백 and signal
cards (2026-10-27 audit). The regex is the twin of `technologies.catalog.NOT_A_TECHNOLOGY`.
Card keywords themselves are untouched; only the derived keys are recomputed.

Revision ID: 0042
Revises: 0041
"""

from alembic import op

NOISE = r"^([0-9]+(\.[0-9]+)*|v[0-9]+(\.[0-9]+)+|(cve|euvd)[0-9]{8,}|cvss.*[0-9].*)$"
FUNCTION = r"""
CREATE OR REPLACE FUNCTION canonical_keyword_keys(keywords jsonb) RETURNS jsonb
LANGUAGE sql STABLE AS $$
  SELECT coalesce(jsonb_agg(key ORDER BY pos), '[]'::jsonb) FROM (
    SELECT key, min(pos) AS pos FROM (
      SELECT coalesce(a.technology_key, n.k) AS key, n.pos
      FROM (
        SELECT lower(regexp_replace(ltrim(btrim(e.value), '#'), '[\s\-_·]', '', 'g')) AS k, e.pos
        FROM jsonb_array_elements_text(coalesce(keywords, '[]'::jsonb))
             WITH ORDINALITY AS e(value, pos)
      ) n
      LEFT JOIN technology_aliases a ON a.alias = n.k
      WHERE n.k <> ''{noise}
    ) m GROUP BY key
  ) d
$$
"""
RECOMPUTE = (
    "UPDATE item_cards SET technology_keys = canonical_keyword_keys(keywords) "
    "WHERE technology_keys IS DISTINCT FROM canonical_keyword_keys(keywords)"
)

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(FUNCTION.replace("{noise}", f" AND n.k !~ '{NOISE}'"))
    op.execute(RECOMPUTE)


def downgrade() -> None:
    op.execute(FUNCTION.replace("{noise}", ""))
    op.execute(RECOMPUTE)
