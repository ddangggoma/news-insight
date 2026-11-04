"""Per-paper signals for the 연구 menu's 주목 문헌 (plan 19 §1), rebuilt after the daily counts.

The documents list reads research_signals instead of scanning the corpus per request: one row
per research document of the SIGNAL_DAYS days up to `through` (the counts' as_of), with the
field, companies and institutions the list filters by and the score it ranks by. Everything is
counted up to the end of `through`, like the counts.

Listings of one paper fold: an arXiv preprint and its Hugging Face daily-papers page, or a
paper found by DOI and by arXiv id, share a canon key (arxiv:<id>, else doi:<doi>), taken from
the paper's own identifier (the DOI OpenAlex confirmed, else a DOI or arXiv id in its URL or
stable id; never a DOI its abstract only cites). The group's lead carries the group's signals.
"""

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Float, and_, case, cast, delete, func, insert, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.freshness import fresh_condition
from news_insight.content.models import Item, ItemDedup, ItemMetricSnapshot
from news_insight.insights.stats import KST, OTHER, day_bounds
from news_insight.research.models import EnrichStatus, ResearchMeta, ResearchSignal
from news_insight.research.openalex import ARXIV_DOI
from news_insight.research.service import REF_KINDS, pick_lookup, research_documents
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from news_insight.spotlight.candidates import HF_PAPERS
from news_insight.stories.models import ItemRef
from news_insight.taxonomy.catalog import FIELD_KEYS

SIGNAL_DAYS = 100  # the longest window (a quarter, 90 days) and some slack
MENTION_LEAD_DAYS = 7  # news citing a paper a few days before its listing date still counts
MENTION_WEIGHT = 10
CITATION_WEIGHT = 5
ORG_MAX = 200
INSERT_CHUNK = 5000


@dataclass
class SignalsResult:
    rows: int = 0
    leads: int = 0
    mentioned: int = 0


@dataclass
class _Doc:
    item_id: int
    occurred_at: datetime
    field: str
    canon: str | None
    company_keys: list[str]
    orgs: list[str]
    enriched: bool
    hf: bool
    cited_growth: int
    upvotes: int = 0


def canon_key(doi: str | None) -> str | None:
    """arxiv:<id> for an arXiv DOI (version dropped), else doi:<doi>; lower case."""
    if not doi:
        return None
    value = doi.strip().lower()
    if value.startswith(ARXIV_DOI):
        arxiv = value.removeprefix(ARXIV_DOI)
        head, sep, version = arxiv.rpartition("v")
        if sep and version.isdigit() and head:
            arxiv = head
        return f"arxiv:{arxiv}"[:320]
    return f"doi:{value}"[:320]


def ref_canon(kind: str, value: str) -> str | None:
    if kind == "arxiv":
        return canon_key(f"{ARXIV_DOI}{value}")
    if kind == "doi":
        return canon_key(value)
    return None


def citation_growth(counts_by_year: Iterable[dict[str, Any]] | None, year: int) -> int:
    """Citations of `year` minus the year before, never below 0."""
    by_year = {
        int(entry["year"]): int(entry.get("cited_by_count") or 0)
        for entry in counts_by_year or []
        if isinstance(entry, dict) and entry.get("year") is not None
    }
    return max(by_year.get(year, 0) - by_year.get(year - 1, 0), 0)


def score_of(mentions: int, upvotes: int, cited_growth: int) -> float:
    return round(
        MENTION_WEIGHT * mentions + upvotes + CITATION_WEIGHT * math.log1p(cited_growth), 3
    )


def _docs(session: Session, start: datetime, end: datetime, year: int) -> list[_Doc]:
    rows = session.execute(
        select(
            Item.id,
            Item.occurred_at,
            Item.url,
            Item.stable_id,
            Item.title,
            Source.operator,
            ItemCard.field,
            ResearchMeta.status,
            ResearchMeta.doi,
            ResearchMeta.company_keys,
            ResearchMeta.institutions,
            ResearchMeta.counts_by_year,
        )
        .select_from(Item)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, and_(ItemCard.item_id == Item.id, ItemCard.status == CardStatus.READY))
        .outerjoin(ResearchMeta, ResearchMeta.item_id == Item.id)
        .where(
            *research_documents(),
            fresh_condition(),
            Item.occurred_at >= start,
            Item.occurred_at < end,
        )
    ).all()
    refs: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for item_id, kind, value in session.execute(
        select(ItemRef.item_id, ItemRef.kind, ItemRef.value)
        .join(Item, Item.id == ItemRef.item_id)
        .join(Source, Source.id == Item.source_id)
        .where(
            ItemRef.kind.in_(REF_KINDS),
            *research_documents(),
            Item.occurred_at >= start,
            Item.occurred_at < end,
        )
    ):
        refs[item_id].append((kind, value))
    docs = []
    for row in rows:
        enriched = row.status == EnrichStatus.OK
        own = row.doi if enriched and row.doi else None
        if own is None:
            lookup = pick_lookup(row.id, row.title, row.stable_id, row.url, refs.get(row.id, []))
            if lookup is not None and lookup.doi and not lookup.verify_title:
                own = lookup.doi
        docs.append(
            _Doc(
                item_id=row.id,
                occurred_at=row.occurred_at,
                field=row.field if row.field in FIELD_KEYS else OTHER,
                canon=canon_key(own),
                company_keys=list(row.company_keys or []),
                orgs=list(
                    dict.fromkeys(
                        str(i["name"])[:ORG_MAX]
                        for i in row.institutions or []
                        if isinstance(i, dict) and i.get("name") and not i.get("company_key")
                    )
                ),
                enriched=enriched,
                hf=row.operator == HF_PAPERS,
                cited_growth=citation_growth(row.counts_by_year, year),
            )
        )
    return docs


def _mentions(session: Session, start: datetime, end: datetime) -> dict[str, set[int]]:
    """canon key → news and community items citing it, first seen in [start, end); repeats of
    an earlier item left out unless they share a known article (spotlight's ELIGIBLE)."""
    eligible = (ItemDedup.duplicate_of.is_(None)) | (ItemDedup.matched_by == "link")
    carriers: dict[str, set[int]] = defaultdict(set)
    for item_id, kind, value in session.execute(
        select(ItemRef.item_id, ItemRef.kind, ItemRef.value)
        .join(Item, Item.id == ItemRef.item_id)
        .outerjoin(ItemDedup, ItemDedup.item_id == Item.id)
        .where(
            ItemRef.kind.in_(REF_KINDS),
            Item.track.in_((Track.NEWS, Track.COMMUNITY)),
            Item.canary.is_(False),
            Item.first_seen_at >= start,
            Item.first_seen_at < end,
            eligible,
        )
    ):
        if (key := ref_canon(kind, value)) is not None:
            carriers[key].add(item_id)
    return carriers


def _upvotes(session: Session, ids: list[int], end: datetime) -> dict[int, int]:
    if not ids:
        return {}
    value = ItemMetricSnapshot.metrics["upvotes"]
    number = case((func.jsonb_typeof(value) == "number", cast(value.as_float(), Float)))
    return {
        item_id: int(upvotes)
        for item_id, upvotes in session.execute(
            select(ItemMetricSnapshot.item_id, func.max(number))
            .where(ItemMetricSnapshot.item_id.in_(ids), ItemMetricSnapshot.captured_at < end)
            .group_by(ItemMetricSnapshot.item_id)
        )
        if upvotes is not None
    }


def recompute_signals(
    session: Session, *, through: date, days: int = SIGNAL_DAYS, now: datetime | None = None
) -> SignalsResult:
    """Rebuild research_signals for the research documents of the `days` KST days up to
    `through` (the whole table: older rows are dropped)."""
    start = day_bounds(through - timedelta(days=days - 1))[0]
    end = day_bounds(through)[1]
    computed_at = now or datetime.now(UTC)
    docs = _docs(session, start, end, through.year)
    carriers = _mentions(session, start - timedelta(days=MENTION_LEAD_DAYS), end)
    upvotes = _upvotes(session, [d.item_id for d in docs if d.hf], end)
    for doc in docs:
        doc.upvotes = upvotes.get(doc.item_id, 0)
    groups: dict[str, list[_Doc]] = defaultdict(list)
    for doc in docs:
        groups[doc.canon or f"item:{doc.item_id}"].append(doc)
    rows: list[dict[str, Any]] = []
    result = SignalsResult()
    for key, members in groups.items():
        members.sort(key=lambda d: (not d.enriched, d.hf, d.occurred_at, d.item_id))
        lead = members[0]
        mentions = len(carriers.get(key, ())) if not key.startswith("item:") else 0
        upvote = max(d.upvotes for d in members)
        growth = max(d.cited_growth for d in members)
        field = next((d.field for d in members if d.field != OTHER), OTHER)
        result.leads += 1
        result.mentioned += mentions > 0
        for doc in members:
            is_lead = doc is lead
            rows.append(
                {
                    "item_id": doc.item_id,
                    "occurred_at": doc.occurred_at,
                    "day": doc.occurred_at.astimezone(KST).date(),
                    "field": field if is_lead else doc.field,
                    "company_keys": sorted({k for d in members for k in d.company_keys})
                    if is_lead
                    else doc.company_keys,
                    "orgs": list(dict.fromkeys(o for d in members for o in d.orgs))
                    if is_lead
                    else doc.orgs,
                    "canon_key": doc.canon,
                    "lead": is_lead,
                    "lead_id": lead.item_id,
                    "mentions": mentions if is_lead else 0,
                    "upvotes": upvote if is_lead else doc.upvotes,
                    "cited_growth": growth if is_lead else doc.cited_growth,
                    "score": score_of(mentions, upvote, growth) if is_lead else 0.0,
                    "computed_at": computed_at,
                }
            )
    session.execute(delete(ResearchSignal))
    for i in range(0, len(rows), INSERT_CHUNK):
        session.execute(insert(ResearchSignal), rows[i : i + INSERT_CHUNK])
    session.flush()
    result.rows = len(rows)
    return result
