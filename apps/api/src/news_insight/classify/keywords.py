"""Keyword normalisation: free-text card keywords → canonical keywords that can be counted.

Two forms per keyword:
- `clean_keyword`: the display form (NFKC, trimmed, `#` and quotes stripped, single spaces).
- `keyword_key`: the matching form (clean, case-folded, without spaces or separators), so
  "온디바이스AI", "온디바이스 AI" and "#온디바이스-ai" are one keyword.
A small curated seed (`catalog/keyword_aliases.yaml`) maps known variants to one canonical
name, e.g. "On-device AI" → "온디바이스 AI".
"""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_ALIAS_PATH = Path(__file__).resolve().parents[3] / "catalog" / "keyword_aliases.yaml"
MAX_KEYWORD_LENGTH = 80
_SPACES = re.compile(r"\s+")
_SEPARATORS = re.compile(r"[\s\-_·•‧・]+")
_WRAPPERS = "#\"'`“”‘’「」『』()[]<> "


def clean_keyword(text: str) -> str | None:
    value = unicodedata.normalize("NFKC", text)
    value = _SPACES.sub(" ", value).strip(_WRAPPERS).strip()
    return value[:MAX_KEYWORD_LENGTH] or None


def keyword_key(text: str) -> str | None:
    value = clean_keyword(text)
    if value is None:
        return None
    return _SEPARATORS.sub("", value.casefold())[:MAX_KEYWORD_LENGTH] or None


class AliasSeedError(Exception):
    """The alias seed file is missing or invalid."""


class _SeedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical: str = Field(min_length=1, max_length=MAX_KEYWORD_LENGTH)
    aliases: tuple[str, ...] = ()


class _SeedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    keywords: tuple[_SeedEntry, ...]


@dataclass(frozen=True)
class AliasSeed:
    """Matching key → canonical display name, from the curated alias file."""

    by_key: dict[str, str]

    def canonical(self, text: str) -> str | None:
        key = keyword_key(text)
        return self.by_key.get(key) if key else None


def load_alias_seed(path: Path = DEFAULT_ALIAS_PATH) -> AliasSeed:
    try:
        data = _SeedFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise AliasSeedError(f"invalid keyword alias seed {path}: {exc}") from exc
    by_key: dict[str, str] = {}
    for entry in data.keywords:
        canonical = clean_keyword(entry.canonical)
        if canonical is None:
            raise AliasSeedError(f"empty canonical keyword in {path}")
        for variant in (canonical, *entry.aliases):
            key = keyword_key(variant)
            if key is None:
                continue
            if by_key.get(key, canonical) != canonical:
                raise AliasSeedError(
                    f"alias '{variant}' maps to both '{by_key[key]}' and '{canonical}'"
                )
            by_key[key] = canonical
    return AliasSeed(by_key=by_key)


@lru_cache
def get_alias_seed() -> AliasSeed:
    return load_alias_seed()
