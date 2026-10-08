"""pgvector copy of the title embeddings (plan 15-6).

`item_embeddings.vector` (real[], written by the story merger) stays; `embedding` mirrors it
as vector(1024) through a trigger, so the taxonomy workspace can search by similarity while the
writers stay unchanged. No ANN index: an HNSW build took 7.6 min on the live data (2026-10-08)
and an exact scan of ~90k vectors serves console queries. Needs the pgvector extension
(the ops/postgres image).

Revision ID: 0033
Revises: 0032
"""

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

MIRROR_FUNCTION = """
CREATE OR REPLACE FUNCTION item_embeddings_mirror() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.embedding := CASE WHEN array_length(NEW.vector, 1) = 1024
                        THEN NEW.vector::vector(1024) END;
  RETURN NEW;
END
$$
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "item_embeddings",
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
    )
    op.execute(
        "UPDATE item_embeddings SET embedding = vector::vector(1024)"
        " WHERE array_length(vector, 1) = 1024"
    )
    op.execute(MIRROR_FUNCTION)
    op.execute(
        "CREATE TRIGGER item_embeddings_mirror BEFORE INSERT OR UPDATE OF vector"
        " ON item_embeddings FOR EACH ROW EXECUTE FUNCTION item_embeddings_mirror()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS item_embeddings_mirror ON item_embeddings")
    op.execute("DROP FUNCTION IF EXISTS item_embeddings_mirror()")
    op.drop_column("item_embeddings", "embedding")
