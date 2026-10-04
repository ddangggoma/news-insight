"""Card classification taxonomy (field, product, impact) loaded from `catalog/taxonomy.yaml`.

The YAML file is the only source of truth: editing it and bumping `revision` changes what
the card engines are asked for, what is accepted from them and what the console shows.
Keys the file does not define are dropped wherever they appear (fail-closed).
"""

from collections import Counter
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[3] / "catalog" / "taxonomy.yaml"


class Axis(StrEnum):
    FIELD = "field"
    PRODUCT = "product"
    IMPACT = "impact"


# Property names used in the engines' JSON output, per axis.
OUTPUT_KEYS: dict[Axis, str] = {
    Axis.FIELD: "fields",
    Axis.PRODUCT: "products",
    Axis.IMPACT: "impact",
}
AXIS_TITLES: dict[Axis, str] = {
    Axis.FIELD: "기술 분야",
    Axis.PRODUCT: "제품군",
    Axis.IMPACT: "영향",
}


# Node keys per axis for one item, e.g. {FIELD: ["ai"], PRODUCT: [], IMPACT: ["watch"]}.
Labels = dict[Axis, list[str]]


class TaxonomyError(Exception):
    """The taxonomy file is missing or invalid."""


class TaxonomyNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=300)
    examples: tuple[str, ...] = ()


class TaxonomyAxis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[TaxonomyNode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_keys(self) -> "TaxonomyAxis":
        counts = Counter(node.key for node in self.nodes)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate keys: {', '.join(duplicates)}")
        return self


class TaxonomyRules(BaseModel):
    """Per-item label limits and free-text rules (impact is always exactly one)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_fields: int = Field(ge=1, le=10)
    max_products: int = Field(ge=1, le=10)
    guidance: tuple[str, ...] = ()


class Taxonomy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    revision: int = Field(ge=1)
    rules: TaxonomyRules
    axes: dict[Axis, TaxonomyAxis]

    @model_validator(mode="after")
    def _every_axis(self) -> "Taxonomy":
        missing = [axis.value for axis in Axis if axis not in self.axes]
        if missing:
            raise ValueError(f"missing axes: {', '.join(missing)}")
        return self

    def nodes(self, axis: Axis) -> tuple[TaxonomyNode, ...]:
        return self.axes[axis].nodes

    def keys(self, axis: Axis) -> tuple[str, ...]:
        return tuple(node.key for node in self.axes[axis].nodes)

    def max_labels(self, axis: Axis) -> int:
        if axis is Axis.FIELD:
            return self.rules.max_fields
        if axis is Axis.PRODUCT:
            return self.rules.max_products
        return 1

    def label(self, axis: Axis, key: str) -> str | None:
        for node in self.axes[axis].nodes:
            if node.key == key:
                return node.label
        return None

    def pick(self, axis: Axis, values: list[Any]) -> list[str]:
        """Known keys in the given order, without duplicates, capped at the axis limit."""
        known = set(self.keys(axis))
        picked: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            key = value.strip().lower()
            if key in known and key not in picked:
                picked.append(key)
        return picked[: self.max_labels(axis)]

    def prompt(self) -> str:
        """Allowed keys with labels and descriptions, plus the classification rules."""
        lines = [f"분류 체계 (revision {self.revision}) — 아래 키만 쓴다:"]
        for axis in Axis:
            limit = self.max_labels(axis)
            count = "정확히 1개" if axis is Axis.IMPACT else f"0~{limit}개"
            lines.append(f"[{OUTPUT_KEYS[axis]}] {AXIS_TITLES[axis]}, {count}")
            for node in self.nodes(axis):
                line = f"  {node.key}: {node.label} — {node.description}"
                if node.examples:
                    line += f" (예: {', '.join(node.examples)})"
                lines.append(line)
        if self.rules.guidance:
            lines.append("분류 규칙:")
            lines.extend(f"  - {rule}" for rule in self.rules.guidance)
        return "\n".join(lines)


def load_taxonomy(path: Path = DEFAULT_TAXONOMY_PATH) -> Taxonomy:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise TaxonomyError(f"cannot read taxonomy {path}: {exc}") from exc
    try:
        return Taxonomy.model_validate(data)
    except ValidationError as exc:
        raise TaxonomyError(f"invalid taxonomy {path}: {exc}") from exc


@lru_cache
def get_taxonomy() -> Taxonomy:
    """The shipped taxonomy, loaded once per process."""
    return load_taxonomy()
