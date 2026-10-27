"""Technology registry seed (`catalog/technologies.yaml`) and keyword normalisation."""

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_TECHNOLOGIES_PATH = Path(__file__).resolve().parents[3] / "catalog" / "technologies.yaml"
STRIP = re.compile(r"[\s\-_·]")
# Normalised keywords that name no technology: bare numbers and versions ("2026", "3.1",
# "v3.1"), vulnerability ids ("cve2026109618") and CVSS scores ("cvssv3.1", "cvss9.8").
# EUVD/CVE bot toots put them on ~18k cards (2026-10-27 audit). Twin of the regex in the
# `canonical_keyword_keys` SQL function (migration 0042); "v8", "5g" and "cve" stay.
NOT_A_TECHNOLOGY = r"^([0-9]+(\.[0-9]+)*|v[0-9]+(\.[0-9]+)+|(cve|euvd)[0-9]{8,}|cvss.*[0-9].*)$"
_NOT_A_TECHNOLOGY = re.compile(NOT_A_TECHNOLOGY)


def normalize(text: str) -> str:
    """Keyword key: lower case without spaces, hyphens, underscores or middle dots."""
    return STRIP.sub("", text.strip().lower().lstrip("#"))


def is_technology_key(key: str) -> bool:
    return bool(key) and _NOT_A_TECHNOLOGY.match(key) is None


class TechKind(StrEnum):
    TECHNOLOGY = "technology"
    STANDARD = "standard"
    REGULATION = "regulation"
    PRODUCT_FAMILY = "product_family"


class TechStatus(StrEnum):
    ACTIVE = "active"
    WATCH = "watch"  # tracked, promoted to active by the monthly review
    IGNORED = "ignored"  # a frequent keyword judged not to be a technology


class TechEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    theme: str | None = None
    aliases: list[str] = Field(default_factory=list)
    kind: TechKind = TechKind.TECHNOLOGY
    status: TechStatus = TechStatus.ACTIVE

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if normalize(value) != value:
            raise ValueError(f"key '{value}' must already be normalised ('{normalize(value)}')")
        return value

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(normalize(alias) for alias in value if normalize(alias)))


class TechCatalog(BaseModel):
    version: int = 1
    technologies: list[TechEntry]

    @model_validator(mode="after")
    def _unique(self) -> "TechCatalog":
        keys = [entry.key for entry in self.technologies]
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            raise ValueError(f"duplicate technology keys: {', '.join(duplicates)}")
        owners: dict[str, str] = {}
        for entry in self.technologies:
            for alias in entry.aliases:
                if alias in keys and alias != entry.key:
                    raise ValueError(f"alias '{alias}' of {entry.key} is itself a technology key")
                if owners.setdefault(alias, entry.key) != entry.key:
                    raise ValueError(f"alias '{alias}' maps to {owners[alias]} and {entry.key}")
        return self


def load_technologies(path: Path = DEFAULT_TECHNOLOGIES_PATH) -> TechCatalog:
    return TechCatalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@lru_cache
def seed_alias_map() -> dict[str, str]:
    """alias → key from the bundled seed (used before the database registry is seeded)."""
    return {
        alias: entry.key for entry in load_technologies().technologies for alias in entry.aliases
    }
