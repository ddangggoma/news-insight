"""Company registry seed (`catalog/companies.yaml`, plan 12): who the cards are about."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from news_insight.taxonomy.catalog import THEME_KEYS
from news_insight.technologies.catalog import normalize

DEFAULT_COMPANIES_PATH = Path(__file__).resolve().parents[3] / "catalog" / "companies.yaml"
MIN_ALIAS = 2  # one-syllable Korean names (롬, 델) are words, not companies
MAX_THEMES = 8


class CompanyKind(StrEnum):
    COMPANY = "company"
    STARTUP = "startup"
    INSTITUTE = "institute"
    REGULATOR = "regulator"
    STANDARDS_BODY = "standards_body"


ORGANIZATIONS = frozenset(
    {CompanyKind.INSTITUTE, CompanyKind.REGULATOR, CompanyKind.STANDARDS_BODY}
)


class CompanyRegion(StrEnum):
    KR = "kr"
    US = "us"
    CN = "cn"
    JP = "jp"
    TW = "tw"
    EU = "eu"
    OTHER = "other"


class Relation(StrEnum):
    """Relation to Samsung DX."""

    SELF = "self"
    COMPETITOR = "competitor"
    SUPPLIER = "supplier"
    PARTNER = "partner"
    PEER = "peer"


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    WATCH = "watch"  # promoted from the candidate queue, not yet reviewed
    IGNORED = "ignored"  # a frequent name judged not worth tracking


class CompanyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=MIN_ALIAS, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    name_ko: str | None = Field(default=None, max_length=120)
    kind: CompanyKind = CompanyKind.COMPANY
    region: CompanyRegion = CompanyRegion.OTHER
    relation: Relation = Relation.PEER
    themes: list[str] = Field(default_factory=list, max_length=MAX_THEMES)
    domains: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    status: CompanyStatus = CompanyStatus.ACTIVE

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if normalize(value) != value:
            raise ValueError(f"key '{value}' must already be normalised ('{normalize(value)}')")
        return value

    @field_validator("themes")
    @classmethod
    def _themes(cls, value: list[str]) -> list[str]:
        unknown = [theme for theme in value if theme not in THEME_KEYS]
        if unknown:
            raise ValueError(f"unknown themes: {', '.join(unknown)}")
        return list(dict.fromkeys(value))

    @field_validator("domains")
    @classmethod
    def _domains(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(d.strip().lower().removeprefix("www.") for d in value if d))

    @property
    def match_names(self) -> list[str]:
        """Normalised spellings that tag a card with this company (key first)."""
        names = [self.key, normalize(self.name), normalize(self.name_ko or "")]
        names += [normalize(alias) for alias in self.aliases]
        return [n for n in dict.fromkeys(names) if len(n) >= MIN_ALIAS]


class CompanyCatalog(BaseModel):
    version: int = 1
    companies: list[CompanyEntry]

    @model_validator(mode="after")
    def _unique(self) -> "CompanyCatalog":
        keys = [entry.key for entry in self.companies]
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            raise ValueError(f"duplicate company keys: {', '.join(duplicates)}")
        owners: dict[str, str] = {}
        for entry in self.companies:
            for name in entry.match_names:
                if owners.setdefault(name, entry.key) != entry.key:
                    raise ValueError(f"name '{name}' maps to {owners[name]} and {entry.key}")
        return self


def load_companies(path: Path = DEFAULT_COMPANIES_PATH) -> CompanyCatalog:
    return CompanyCatalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@lru_cache
def seed_alias_map() -> dict[str, str]:
    """name → key from the bundled seed (fixtures and tests)."""
    return {name: entry.key for entry in load_companies().companies for name in entry.match_names}
