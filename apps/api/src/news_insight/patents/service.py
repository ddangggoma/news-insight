"""patents.index (plan 19 §2.2): patent_meta for office publications and patent news.

Hourly at :25. Items from `patent_office` sources (the EPS pilot, EPO OPS once its key is in
.env) and items whose card is marked intellectual property (signal_type "ip") get a row: new
items first, newest first, then items whose card was rewritten since they were indexed. A news
item whose card is no longer "ip" loses its row.

- EPS pilot: publication number from the stable id ("epo:EP4815726NWA1"), IPC from the
  summary ("EP4815726NWA1; IPC: G06N 3/08, …"); the author is the office, not an applicant.
- OPS: applicants from the author ("A; B", collect/epo_ops.py), classifications from the
  summary if present, else the CPC the source's query asks for (`config.cql`).
- News: the card's field and companies, and the first patent number the text cites.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import case, delete, exists, or_, select, union
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.companies.service import alias_map, match_company
from news_insight.content.models import Item, ItemDedup
from news_insight.patents.classification import (
    OTHER,
    codes_from_query,
    codes_from_summary,
    fields_for,
    parse_publication,
)
from news_insight.patents.models import PatentMeta, PatentSource
from news_insight.sources.models import Source
from news_insight.stories.models import ItemRef
from news_insight.stories.refs import PATENT

logger = logging.getLogger(__name__)

MAX_PER_RUN = 5000
PATENT_OFFICE = "patent_office"
IP_SIGNAL = "ip"
APPLICANT_MAX = 300


@dataclass
class IndexResult:
    indexed: int = 0
    removed: int = 0


def patent_documents() -> Any:
    """Ids of the items that count as patent documents: office publications and ip cards
    (a union: one OR across both tables scanned every item, 6.8 s on the live data)."""
    office = select(Item.id).join(Source, Source.id == Item.source_id)
    ip_cards = select(ItemCard.item_id).where(
        ItemCard.status == CardStatus.READY, ItemCard.signal_type == IP_SIGNAL
    )
    return union(office.where(Source.category == PATENT_OFFICE), ip_cards)


def _not_repeat() -> Any:
    return ~exists().where(ItemDedup.item_id == Item.id, ItemDedup.duplicate_of.is_not(None))


def _source_kind(source: Source) -> PatentSource:
    if source.category != PATENT_OFFICE:
        return PatentSource.NEWS
    return PatentSource.OPS if source.config.get("mode") == "epo_ops" else PatentSource.EPS


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def build_meta(
    item: Item,
    source: Source,
    item_card: ItemCard | None,
    patent_refs: list[str],
    aliases: dict[str, str],
    now: datetime,
) -> dict[str, Any]:
    """Column values of an item's patent_meta row."""
    kind = _source_kind(source)
    ready = item_card if item_card is not None and item_card.status == CardStatus.READY else None
    cpc: list[str] = []
    ipc: list[str] = []
    applicants: list[str] = []
    if kind == PatentSource.NEWS:
        number, code, office = (
            parse_publication(patent_refs[0]) if patent_refs else (None, None, None)
        )
    else:
        number, code, office = parse_publication(item.stable_id)
        cpc, ipc = codes_from_summary(item.summary)
        if kind == PatentSource.OPS:
            cpc = _unique([*cpc, *codes_from_query(str(source.config.get("cql") or ""))])
            applicants = _unique(
                [name.strip()[:APPLICANT_MAX] for name in (item.author or "").split(";")]
            )
    keys = [match_company(name, aliases) for name in applicants]
    company_keys = _unique([k for k in keys if k] + list(ready.company_keys if ready else []))
    fields = fields_for([*cpc, *ipc])
    if not fields:
        fields = [ready.field if ready is not None and ready.field else OTHER]
    return {
        "publication_number": number,
        "kind": code,
        "office": office,
        "cpc": cpc,
        "ipc": ipc,
        "applicants": applicants,
        "company_keys": company_keys,
        "field": fields[0],
        "fields": fields,
        "source": kind,
        "indexed_at": now,
    }


def cited_order(item: Item, refs: list[str]) -> list[str]:
    """The item's patent references in the order its text cites them (URL, title, summary:
    the texts stories.refs reads), then any left over alphabetically."""
    found: list[str] = []
    for match in PATENT.finditer(" ".join(t for t in (item.url, item.title, item.summary) if t)):
        value = re.sub(r"[\s,]", "", match.group(1)).upper()
        if value in refs and value not in found:
            found.append(value)
    return found + sorted(set(refs) - set(found))


def remove_stale_news(session: Session) -> int:
    """News rows whose card is no longer an ip card (reclassified or failed)."""
    stale = (
        select(PatentMeta.item_id)
        .join(ItemCard, ItemCard.item_id == PatentMeta.item_id, isouter=True)
        .where(
            PatentMeta.source == PatentSource.NEWS,
            or_(
                ItemCard.id.is_(None),
                ItemCard.status != CardStatus.READY,
                ItemCard.signal_type.is_distinct_from(IP_SIGNAL),
            ),
        )
    )
    result = session.execute(delete(PatentMeta).where(PatentMeta.item_id.in_(stale)))
    return int(getattr(result, "rowcount", 0) or 0)


def index_patents(session: Session, *, now: datetime, limit: int = MAX_PER_RUN) -> IndexResult:
    result = IndexResult(removed=remove_stale_news(session))
    rows = session.execute(
        select(Item, Source, ItemCard)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .outerjoin(PatentMeta, PatentMeta.item_id == Item.id)
        .where(
            Item.id.in_(patent_documents()),
            Item.canary.is_(False),
            _not_repeat(),
            or_(PatentMeta.item_id.is_(None), ItemCard.generated_at > PatentMeta.indexed_at),
        )
        .order_by(
            case((PatentMeta.item_id.is_(None), 0), else_=1),
            Item.occurred_at.desc(),
            Item.id.desc(),
        )
        .limit(limit)
    ).all()
    if not rows:
        session.flush()
        return result
    ids = [item.id for item, _, _ in rows]
    refs: dict[int, list[str]] = {}
    for item_id, value in session.execute(
        select(ItemRef.item_id, ItemRef.value)
        .where(ItemRef.item_id.in_(ids), ItemRef.kind == "patent")
        .order_by(ItemRef.item_id, ItemRef.value)
    ):
        refs.setdefault(item_id, []).append(value)
    aliases = alias_map(session)
    for item, source, item_card in rows:
        cited = cited_order(item, refs.get(item.id, []))
        values = build_meta(item, source, item_card, cited, aliases, now)
        row = session.get(PatentMeta, item.id)
        if row is None:
            session.add(PatentMeta(item_id=item.id, **values))
        else:
            for name, value in values.items():
                setattr(row, name, value)
        result.indexed += 1
    session.flush()
    logger.info("patents index: indexed=%d removed=%d", result.indexed, result.removed)
    return result
