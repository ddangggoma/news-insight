"""Reader API for the public web. Reached only by the web server over the internal network."""

from collections.abc import Sequence

from fastapi import APIRouter, Depends

from news_insight.public.auth import require_public_key
from news_insight.public.schemas import TaxonomyField, TaxonomyNode, TaxonomyOut
from news_insight.taxonomy.catalog import (
    BUSINESSES,
    FIELDS,
    IMPACTS,
    SCOPES,
    TAXONOMY_REVISION,
    Node,
)

router = APIRouter(
    prefix="/api/public", tags=["public"], dependencies=[Depends(require_public_key)]
)


def _nodes(values: Sequence[Node]) -> list[TaxonomyNode]:
    return [TaxonomyNode(key=node.key, label=node.name) for node in values]


@router.get("/taxonomy")
def get_taxonomy() -> TaxonomyOut:
    return TaxonomyOut(
        revision=TAXONOMY_REVISION,
        fields=[
            TaxonomyField(key=field.key, label=field.name, themes=_nodes(field.themes))
            for field in FIELDS
        ],
        businesses=_nodes(BUSINESSES),
        impacts=_nodes(IMPACTS),
        scopes=_nodes(SCOPES),
    )
