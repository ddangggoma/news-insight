"""Let bulk taxonomy changes skip the per-card label trigger (plan 15-4).

A merge or split rewrites thousands of item_cards rows; the trigger relabelled each row and the
change engine then relabelled the same cards again (33 s to preview a 6.5k-card split). The
engine now sets `news.bulk_relabel = on` for its transaction and relabels once at the end.

Revision ID: 0032
Revises: 0031
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION item_cards_sync_labels() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF coalesce(current_setting('news.bulk_relabel', true), '') = 'on' THEN
    RETURN NULL;
  END IF;
  PERFORM relabel_items(ARRAY[NEW.item_id]);
  RETURN NULL;
END
$$
"""

PREVIOUS = """
CREATE OR REPLACE FUNCTION item_cards_sync_labels() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM relabel_items(ARRAY[NEW.item_id]);
  RETURN NULL;
END
$$
"""


def upgrade() -> None:
    op.execute(TRIGGER_FUNCTION)


def downgrade() -> None:
    op.execute(PREVIOUS)
