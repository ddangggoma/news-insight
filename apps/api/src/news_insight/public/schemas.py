"""Reader-facing response models: no source keys, validation state or stored bodies."""

from pydantic import BaseModel


class TaxonomyNode(BaseModel):
    key: str
    label: str


class TaxonomyField(TaxonomyNode):
    themes: list[TaxonomyNode]


class TaxonomyOut(BaseModel):
    revision: str
    fields: list[TaxonomyField]
    businesses: list[TaxonomyNode]
    impacts: list[TaxonomyNode]
    scopes: list[TaxonomyNode]
