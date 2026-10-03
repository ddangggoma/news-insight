"""Declarative source catalog (YAML) and idempotent seeding into the registry."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.sources.enums import (
    AccessMethod,
    PollClass,
    Region,
    SourceStatus,
    StorageRight,
    Track,
    ValidationStage,
)
from news_insight.sources.ladder import reset_validation
from news_insight.sources.models import Source

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[3] / "catalog" / "sources.yaml"
IDENTITY_FIELDS = ("endpoint_url", "official_domain", "access_method")


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
    name: str = Field(min_length=1, max_length=200)
    track: Track
    category: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    access_method: AccessMethod
    endpoint_url: str = Field(max_length=2048)
    official_domain: str = Field(pattern=r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", max_length=253)
    operator: str = Field(min_length=1, max_length=200)
    region: Region
    language: str = Field(pattern=r"^[a-z]{2}(?:-[A-Za-z]{2,4})?$")
    poll_class: PollClass
    dx_relevance: str = Field(min_length=10)
    terms_url: str | None = None
    storage_right: StorageRight | None = None
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint_url", "terms_url")
    @classmethod
    def _absolute_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError(f"must be an absolute http(s) URL: {value}")
        return value


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    sources: list[CatalogEntry]

    @model_validator(mode="after")
    def _unique_keys(self) -> "Catalog":
        counts = Counter(entry.key for entry in self.sources)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate source keys: {', '.join(duplicates)}")
        return self


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> Catalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Catalog.model_validate(raw)


@dataclass(frozen=True)
class SeedResult:
    created: list[str]
    updated: list[str]
    reset: list[str]


def seed_catalog(session: Session, catalog: Catalog) -> SeedResult:
    keys = [entry.key for entry in catalog.sources]
    existing = {
        source.key: source for source in session.scalars(select(Source).where(Source.key.in_(keys)))
    }
    created: list[str] = []
    updated: list[str] = []
    reset: list[str] = []
    for entry in catalog.sources:
        values = entry.model_dump()
        source = existing.get(entry.key)
        if source is None:
            session.add(
                Source(
                    **values,
                    validation_stage=ValidationStage.UNVERIFIED,
                    status=SourceStatus.CANDIDATE,
                )
            )
            created.append(entry.key)
            continue
        identity_changed = any(getattr(source, name) != values[name] for name in IDENTITY_FIELDS)
        changed = False
        for name, value in values.items():
            if getattr(source, name) != value:
                setattr(source, name, value)
                changed = True
        if identity_changed:
            reset_validation(session, source, reason="catalog identity fields changed")
            reset.append(entry.key)
        elif changed:
            updated.append(entry.key)
    session.flush()
    return SeedResult(created=created, updated=updated, reset=reset)
