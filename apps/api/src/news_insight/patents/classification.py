"""Patent classifications (plan 19 §2.2): CPC/IPC codes as stored by the collectors, publication
numbers, and the CPC/IPC → technology field map (catalog/cpc_fields.yaml)."""

import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

from news_insight.taxonomy.catalog import FIELD_KEYS

DEFAULT_CPC_FIELDS_PATH = Path(__file__).resolve().parents[3] / "catalog" / "cpc_fields.yaml"
OTHER = "other"
SUBCLASS = re.compile(r"^[A-HY]\d{2}[A-Z]$")
GROUP = re.compile(r"^[A-HY]\d{2}[A-Z] \d{1,4}$")
# "G06N 3/08", "G06N3/08", "H04W0072040000" (OPS cpci), or a bare subclass "H01M"
_CODE = re.compile(
    r"^\s*([A-HY])\s*(\d{2})\s*([A-Z])"
    r"(?:\s*(?:(\d{1,4})\s*/\s*(\d{1,6})|(\d{4})(\d{6})))?\s*$",
    re.IGNORECASE,
)
_LABELLED = re.compile(r"\b(CPC|IPC)\s*:\s*([^;\n]+)", re.IGNORECASE)
_QUERY_CPC = re.compile(r"\b(?:cpc|ipc|ic)\s*=\s*([A-HY]\d{2}[A-Z](?:\s*\d{1,4}/\d{1,6})?)", re.I)
# EP4815726NWA1 (EPS adds "NW"), US2025123456A1, CN118123456A, US12264976, WO2025/123456
_PUBLICATION = re.compile(r"^(?:EPO:)?([A-Z]{2})(\d[\d/]*\d)(?:[A-Z]*?([A-Z]\d?))?$")


def parse_code(raw: str) -> str | None:
    """A classification symbol as "G06N 3/08" (main group without leading zeros, subgroup as
    written but without the trailing zeros of the fixed-width form), or a bare subclass."""
    match = _CODE.match(raw)
    if not match:
        return None
    section, klass, sub, main, group, wide_main, wide_group = match.groups()
    subclass = f"{section}{klass}{sub}".upper()
    if not SUBCLASS.match(subclass) or subclass.startswith("Z"):
        return None
    if wide_main is not None:
        main, group = wide_main, wide_group.rstrip("0").ljust(2, "0")
    if main is None:
        return subclass
    return f"{subclass} {int(main)}/{group}"


def _unique(codes: Iterable[str | None]) -> list[str]:
    return list(dict.fromkeys(code for code in codes if code))


def codes_from_summary(summary: str | None) -> tuple[list[str], list[str]]:
    """(CPC, IPC) codes from a "CPC: …; IPC: …" summary (the EPS pilot writes
    "EP4815726NWA1; IPC: A01N 25/02, A01N 25/04")."""
    cpc: list[str | None] = []
    ipc: list[str | None] = []
    for label, codes in _LABELLED.findall(summary or ""):
        target = cpc if label.upper() == "CPC" else ipc
        target.extend(parse_code(code) for code in codes.split(","))
    return _unique(cpc), _unique(ipc)


def codes_from_query(cql: str | None) -> list[str]:
    """Classifications an OPS source's query asks for ("pn=US and cpc=G06N"): every document
    it returns carries them, so they stand in until OPS biblio classifications are stored."""
    return _unique(parse_code(code) for code in _QUERY_CPC.findall(cql or ""))


def parse_publication(stable_id: str) -> tuple[str | None, str | None, str | None]:
    """(publication number without kind, kind code, office) from a collector's stable id or a
    patent reference."""
    match = _PUBLICATION.match(stable_id.strip().upper().replace(" ", ""))
    if not match:
        return None, None, None
    office, number, kind = match.groups()
    return f"{office}{number.replace('/', '')}", kind, office


class CpcFieldMap(BaseModel):
    version: int = 1
    subclasses: dict[str, str]
    groups: dict[str, str] = {}

    @field_validator("subclasses", "groups")
    @classmethod
    def _targets(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = sorted(set(value.values()) - FIELD_KEYS)
        if unknown:
            raise ValueError(f"unknown fields: {', '.join(unknown)}")
        return value

    @field_validator("subclasses")
    @classmethod
    def _subclass_keys(cls, value: dict[str, str]) -> dict[str, str]:
        if bad := [key for key in value if not SUBCLASS.match(key)]:
            raise ValueError(f"not subclasses: {', '.join(bad)}")
        return value

    @field_validator("groups")
    @classmethod
    def _group_keys(cls, value: dict[str, str]) -> dict[str, str]:
        if bad := [key for key in value if not GROUP.match(key)]:
            raise ValueError(f"not 'subclass main-group': {', '.join(bad)}")
        return value

    def field_of(self, code: str) -> str | None:
        subclass, _, rest = code.partition(" ")
        main = rest.split("/", 1)[0]
        if main and (field := self.groups.get(f"{subclass} {main}")):
            return field
        return self.subclasses.get(subclass)


@lru_cache
def load_cpc_fields(path: Path = DEFAULT_CPC_FIELDS_PATH) -> CpcFieldMap:
    return CpcFieldMap.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def fields_for(codes: Iterable[str]) -> list[str]:
    """Distinct fields of the codes, in code order (the main classification's field first)."""
    mapping = load_cpc_fields()
    return _unique(mapping.field_of(code) for code in codes)
