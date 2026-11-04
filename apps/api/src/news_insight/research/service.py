"""research.enrich (plan 19 §2.1): OpenAlex metadata for papers that carry a DOI or arXiv id.

Hourly at :20, at most 2000 papers a run: papers never asked first, newest first; then papers
OpenAlex did not know (asked again 7 days later while the paper is under 90 days old), failed
answers (the next day) and found papers older than 30 days (citations, while the paper is under
180 days old). A paused or empty OpenAlex budget, a 429 or five failures in a row end the run;
the next run carries on.
"""

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, exists, or_, select
from sqlalchemy.orm import Session

from news_insight.collect.context import polite_url, provider_headers
from news_insight.collect.contracts import CollectorError
from news_insight.collect.http import fetch_checked
from news_insight.companies.service import alias_map, match_company
from news_insight.content.models import Item, ItemDedup
from news_insight.net.mime import JSON_MIME
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.research.models import EnrichStatus, ResearchMeta
from news_insight.research.openalex import (
    HOST,
    Institution,
    Work,
    doi_for_ref,
    parse_work,
    work_url,
)
from news_insight.scheduling.providers import OPENALEX_WORKS, ProviderGate
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from news_insight.stories.models import ItemRef

logger = logging.getLogger(__name__)

MAX_PER_RUN = 2000
REF_KINDS = ("doi", "arxiv")
# patent offices and IP news share the research_ip track; they are indexed by patents.service
PATENT_CATEGORIES = ("patent_office", "ip_office")
RETRY_NOT_FOUND = timedelta(days=7)
NOT_FOUND_HORIZON = timedelta(days=90)
RETRY_ERROR = timedelta(days=1)
REFRESH_OK = timedelta(days=30)
REFRESH_HORIZON = timedelta(days=180)
MAX_FAILURES_IN_A_ROW = 5
RATE_LIMIT_PAUSE = 3600
COMMIT_EVERY = 100
ERROR_MAX = 500


@dataclass
class EnrichResult:
    attempted: int = 0
    ok: int = 0
    not_found: int = 0
    errors: int = 0
    stopped: str | None = None  # provider_backoff | provider_budget | rate_limited | errors


def research_documents() -> list[Any]:
    """Conditions for an item that counts as a research document (enrichment and stats)."""
    return [
        Item.track == Track.RESEARCH_IP,
        Item.canary.is_(False),
        Source.category.not_in(PATENT_CATEGORIES),
        # a repeat of an earlier item (the same paper from arXiv and OpenAlex) counts once
        ~exists().where(ItemDedup.item_id == Item.id, ItemDedup.duplicate_of.is_not(None)),
    ]


def due_items(session: Session, *, now: datetime, limit: int) -> list[tuple[int, str]]:
    """(item id, DOI to look up) of the papers due, in the order they are asked."""
    meta = ResearchMeta
    due = or_(
        meta.item_id.is_(None),
        and_(
            meta.status == EnrichStatus.NOT_FOUND,
            meta.enriched_at <= now - RETRY_NOT_FOUND,
            Item.occurred_at >= now - NOT_FOUND_HORIZON,
        ),
        and_(meta.status == EnrichStatus.ERROR, meta.enriched_at <= now - RETRY_ERROR),
        and_(
            meta.status == EnrichStatus.OK,
            meta.enriched_at <= now - REFRESH_OK,
            Item.occurred_at >= now - REFRESH_HORIZON,
        ),
    )
    rows = session.execute(
        select(Item.id, Item.url)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(meta, meta.item_id == Item.id)
        .where(
            *research_documents(),
            exists().where(ItemRef.item_id == Item.id, ItemRef.kind.in_(REF_KINDS)),
            due,
        )
        .order_by(
            case((meta.item_id.is_(None), 0), else_=1),
            Item.occurred_at.desc(),
            Item.id.desc(),
        )
        .limit(limit)
    ).all()
    if not rows:
        return []
    refs: dict[int, list[tuple[str, str]]] = {}
    for item_id, kind, value in session.execute(
        select(ItemRef.item_id, ItemRef.kind, ItemRef.value)
        .where(ItemRef.item_id.in_([row.id for row in rows]), ItemRef.kind.in_(REF_KINDS))
        .order_by(ItemRef.item_id, ItemRef.kind.desc(), ItemRef.value)
    ):
        refs.setdefault(item_id, []).append((kind, value))
    due_list = []
    for row in rows:
        doi = pick_doi(refs.get(row.id, []), row.url)
        if doi is not None:
            due_list.append((row.id, doi))
    return due_list


def pick_doi(refs: Iterable[tuple[str, str]], url: str) -> str | None:
    """The paper's own identifier among those its text mentions: the one in its URL, else a
    DOI before an arXiv id (cited papers appear in abstracts too)."""
    candidates = [(kind, value) for kind, value in refs if kind in REF_KINDS]
    lowered = url.lower()
    for kind, value in candidates:
        if value.lower() in lowered:
            return doi_for_ref(kind, value)
    for kind, value in sorted(candidates, key=lambda ref: (ref[0] != "doi", ref[1])):
        return doi_for_ref(kind, value)
    return None


def link_institutions(
    institutions: list[Institution], aliases: dict[str, str]
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """(institutions as stored, company keys, has a company-type institution). Only
    institutions of type "company" are matched against the registry: a university that shares
    a company's name ("Samsung Medical Center" is a hospital) is not that company."""
    stored: list[dict[str, Any]] = []
    keys: list[str] = []
    has_company = False
    for institution in institutions:
        key = None
        if institution.type == "company":
            has_company = True
            key = match_company(institution.name, aliases)
            if key is not None and key not in keys:
                keys.append(key)
        stored.append(institution.as_json(key))
    return stored, keys, has_company


def _row(session: Session, item_id: int, doi: str) -> ResearchMeta:
    row = session.get(ResearchMeta, item_id)
    if row is None:
        row = ResearchMeta(item_id=item_id, doi=doi)
        session.add(row)
    row.doi = doi
    return row


def _save_work(
    session: Session, item_id: int, doi: str, work: Work, aliases: dict[str, str], now: datetime
) -> None:
    institutions, keys, has_company = link_institutions(work.institutions, aliases)
    row = _row(session, item_id, doi)
    row.openalex_id = work.openalex_id
    row.venue = work.venue
    row.oa_field = work.oa_field
    row.oa_subfield = work.oa_subfield
    row.oa_topic = work.oa_topic
    row.institutions = institutions
    row.countries = work.countries
    row.has_company = has_company
    row.company_keys = keys
    row.cited_by = work.cited_by
    row.fwci = work.fwci
    row.counts_by_year = work.counts_by_year
    row.status = EnrichStatus.OK
    row.error = None
    row.enriched_at = now


def _save_status(
    session: Session,
    item_id: int,
    doi: str,
    status: EnrichStatus,
    now: datetime,
    error: str | None = None,
) -> None:
    """A miss or a failure keeps whatever an earlier answer stored."""
    row = _row(session, item_id, doi)
    row.status = status
    row.error = error[:ERROR_MAX] if error else None
    row.enriched_at = now


def enrich(
    session: Session,
    fetcher: SafeFetcher,
    *,
    now: datetime,
    limit: int = MAX_PER_RUN,
    gate: ProviderGate | None = None,
) -> EnrichResult:
    result = EnrichResult()
    due = due_items(session, now=now, limit=limit)
    if not due:
        return result
    aliases = alias_map(session)
    failures = 0
    for item_id, doi in due:
        if gate is not None:
            if gate.backoff_seconds(HOST):
                result.stopped = "provider_backoff"
                break
            if not gate.try_acquire(OPENALEX_WORKS):
                result.stopped = "provider_budget"
                break
        result.attempted += 1
        url = work_url(doi)
        try:
            response = fetch_checked(
                fetcher, polite_url(url), allowed_mime=JSON_MIME, headers=provider_headers(url)
            )
            work = parse_work(json.loads(response.content))
        except CollectorError as exc:
            if exc.status_code == 404:
                _save_status(session, item_id, doi, EnrichStatus.NOT_FOUND, now)
                result.not_found += 1
                failures = 0
                continue
            if exc.code == "rate_limited":
                result.attempted -= 1  # not asked: due again next run
                if gate is not None:
                    gate.back_off(HOST, exc.retry_after or RATE_LIMIT_PAUSE)
                result.stopped = "rate_limited"
                break
            _save_status(session, item_id, doi, EnrichStatus.ERROR, now, f"{exc.code}: {exc}")
        except (ValueError, TypeError, KeyError) as exc:  # not JSON, or not a work
            _save_status(session, item_id, doi, EnrichStatus.ERROR, now, f"parse_error: {exc}")
        else:
            _save_work(session, item_id, doi, work, aliases, now)
            result.ok += 1
            failures = 0
            if result.attempted % COMMIT_EVERY == 0:
                session.commit()  # a long run keeps what it found if it is stopped
            continue
        result.errors += 1
        failures += 1
        if failures >= MAX_FAILURES_IN_A_ROW:
            result.stopped = "errors"
            break
    session.flush()
    logger.info(
        "research enrich: attempted=%d ok=%d not_found=%d errors=%d stopped=%s",
        result.attempted,
        result.ok,
        result.not_found,
        result.errors,
        result.stopped,
    )
    return result
