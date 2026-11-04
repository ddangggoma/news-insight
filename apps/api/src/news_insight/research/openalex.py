"""OpenAlex single-work lookups (plan 19 §2.1): venue, topic, institutions, citations.

`GET /works/doi:<doi>` is a singleton request: OpenAlex charges no credits for it, with or
without a key (x-ratelimit-cost-usd: 0, checked 2026-11-04). arXiv papers are found by their
DataCite DOI, 10.48550/arXiv.<id>. `select=` keeps the answer to the fields stored here (an
answer with the reference list is 30-60 KB, this one 4-12 KB).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote

HOST = "api.openalex.org"
WORKS_URL = f"https://{HOST}/works/"
FIELDS = (
    "id",
    "doi",
    "title",
    "publication_date",
    "primary_location",
    "primary_topic",
    "authorships",
    "cited_by_count",
    "fwci",
    "counts_by_year",
)
DOI_PREFIX = "https://doi.org/"
ARXIV_DOI = "10.48550/arxiv."
NAME_MAX = 200  # institution names (they become org_name in the daily stats)
VENUE_MAX = 300
LABEL_MAX = 120
TOPIC_MAX = 300
# an OpenAlex work id: the stable id of items from the openalex_works preset
OPENALEX_WORK = re.compile(r"^(?:https?://openalex\.org/)?(W\d{4,12})$", re.IGNORECASE)
TITLE_MATCH = 0.75  # SequenceMatcher ratio of the normalised titles


@dataclass(frozen=True)
class Institution:
    name: str
    type: str | None  # OpenAlex: company, education, facility, government, healthcare, ...
    country: str | None  # ISO alpha-2
    ror: str | None

    def as_json(self, company_key: str | None = None) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "country": self.country,
            "ror": self.ror,
            "company_key": company_key,
        }


@dataclass(frozen=True)
class Work:
    openalex_id: str | None
    doi: str | None
    title: str | None
    venue: str | None
    oa_field: str | None
    oa_subfield: str | None
    oa_topic: str | None
    institutions: list[Institution] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    cited_by: int = 0
    fwci: float | None = None
    counts_by_year: list[dict[str, int]] = field(default_factory=list)


def doi_for_ref(kind: str, value: str) -> str | None:
    """The DOI to look up for an item reference (stories.models.ItemRef), lower case."""
    if kind == "doi":
        return value.strip().lower() or None
    if kind == "arxiv":
        return f"{ARXIV_DOI}{value.strip().lower()}"
    return None


def openalex_work_id(stable_id: str) -> str | None:
    """ "W7224094464" from an openalex_works item's stable id ("https://openalex.org/W…")."""
    match = OPENALEX_WORK.match(stable_id.strip())
    return match.group(1).upper() if match else None


def work_url(doi: str | None = None, *, openalex_id: str | None = None) -> str:
    """Singleton URL by OpenAlex id, else by DOI; the DOI keeps its slashes (OpenAlex routes
    on them) but nothing else that would end or split the path."""
    path = openalex_id if openalex_id else f"doi:{quote(doi or '', safe='/()-._;:')}"
    return f"{WORKS_URL}{path}?select={','.join(FIELDS)}"


def _title_key(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).lower()
    return " ".join(re.findall(r"\w+", folded))


def titles_match(item_title: str, work_title: str | None) -> bool:
    """Whether OpenAlex's work is the item's paper and not one its abstract cites: the
    normalised titles are alike, or one contains the other (subtitles, series prefixes)."""
    a, b = _title_key(item_title), _title_key(work_title or "")
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= TITLE_MATCH


def _short_id(value: Any) -> str | None:
    text = str(value or "").rstrip("/")
    return text.rsplit("/", 1)[-1] or None


def _name(value: Any, limit: int) -> str | None:
    text = " ".join(str(value or "").split())
    return text[:limit] or None


def _label(block: Any, limit: int = LABEL_MAX) -> str | None:
    return _name(block.get("display_name"), limit) if isinstance(block, dict) else None


def parse_work(payload: Any) -> Work:
    """A single-work answer → Work. Missing blocks become None or empty, never errors:
    OpenAlex fills topics, institutions and citations in over the weeks after publication.
    Raises ValueError for an answer that is not a JSON object."""
    if not isinstance(payload, dict):
        raise ValueError(f"expected a work object, got {type(payload).__name__}")
    doi = str(payload.get("doi") or "").lower().removeprefix(DOI_PREFIX) or None
    location = payload.get("primary_location") or {}
    source = location.get("source") if isinstance(location, dict) else None
    topic = payload.get("primary_topic") or {}
    institutions: dict[str, Institution] = {}
    countries: set[str] = set()
    for authorship in payload.get("authorships") or []:
        if not isinstance(authorship, dict):
            continue
        countries.update(str(c).upper() for c in authorship.get("countries") or [] if c)
        for raw in authorship.get("institutions") or []:
            name = _name(raw.get("display_name"), NAME_MAX) if isinstance(raw, dict) else None
            if name is None:
                continue
            country = str(raw.get("country_code") or "").upper() or None
            if country:
                countries.add(country)
            identity = str(raw.get("id") or name)
            institutions.setdefault(
                identity,
                Institution(
                    name=name,
                    type=str(raw.get("type") or "") or None,
                    country=country,
                    ror=str(raw.get("ror") or "") or None,
                ),
            )
    fwci = payload.get("fwci")
    return Work(
        openalex_id=_short_id(payload.get("id")),
        doi=doi,
        title=_name(payload.get("title"), 1000),
        venue=_label(source, VENUE_MAX),
        oa_field=_label(topic.get("field")),
        oa_subfield=_label(topic.get("subfield")),
        oa_topic=_label(topic, TOPIC_MAX),
        institutions=list(institutions.values()),
        countries=sorted(c for c in countries if len(c) == 2),
        cited_by=int(payload.get("cited_by_count") or 0),
        fwci=float(fwci) if isinstance(fwci, int | float) else None,
        counts_by_year=[
            {"year": int(row["year"]), "cited_by_count": int(row.get("cited_by_count") or 0)}
            for row in payload.get("counts_by_year") or []
            if isinstance(row, dict) and row.get("year")
        ],
    )
