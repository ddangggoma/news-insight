"""Papers and patents in the test database (plan 19 research, patents and daily stats)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import AccessMethod, Region, Track, ValidationStage
from news_insight.sources.models import Source
from news_insight.stories.models import ItemRef
from news_insight.taxonomy.catalog import TAXONOMY_REVISION
from tests.factories import build_source

SEEN = datetime(2026, 11, 3, 1, 0, tzinfo=UTC)


def source(
    session: Session,
    key: str,
    *,
    category: str = "academic_index",
    track: Track = Track.RESEARCH_IP,
    config: dict[str, Any] | None = None,
) -> Source:
    row = session.scalars(select(Source).where(Source.key == key)).one_or_none()
    if row is None:
        row = build_source(
            key=key,
            name=key,
            track=track,
            category=category,
            access_method=AccessMethod.RESEARCH_API,
            region=Region.GLOBAL_EN,
            official_domain=f"{key}.org",
            validation_stage=ValidationStage.V4,
            config=config or {},
        )
        session.add(row)
        session.flush()
    return row


def document(
    session: Session,
    src: Source,
    slug: str,
    *,
    published: datetime | None = SEEN,
    seen: datetime = SEEN,
    refs: tuple[tuple[str, str], ...] = (),
    url: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    author: str | None = None,
    stable_id: str | None = None,
    canary: bool = False,
) -> Item:
    link = url or f"https://{src.key}.org/{slug}"
    ingest_items(
        session,
        src,
        [
            RawItem(
                stable_id=stable_id or link,
                url=link,
                title=title or f"Document {slug} about distinct things {slug}",
                published_at=published,
                summary=summary,
                author=author,
            )
        ],
        fetch_run=None,
        now=seen,
        canary=canary,
    )
    item = session.scalars(
        select(Item).where(Item.source_id == src.id, Item.stable_id == (stable_id or link))
    ).one()
    for kind, value in refs:
        session.add(ItemRef(item_id=item.id, kind=kind, value=value, meta={}))
    session.flush()
    return item


def card(
    session: Session,
    item: Item,
    *,
    field: str | None = "ai",
    themes: list[str] | None = None,
    signal_type: str | None = "research",
    companies: list[str] | None = None,
    generated_at: datetime = SEEN,
) -> ItemCard:
    row = ItemCard(
        item_id=item.id,
        status=CardStatus.READY,
        title_ko=f"카드 {item.id}",
        summary_ko=["요약"],
        keywords=[],
        engine="agy",
        model="m",
        input_hash="h",
        attempts=0,
        generated_at=generated_at,
        field=field,
        themes=themes
        if themes is not None
        else ([f"{field}__foundation_models"] if field == "ai" else []),
        signal_type=signal_type,
        scope="dx",
        taxonomy_revision=TAXONOMY_REVISION,
        companies=companies or [],
    )
    session.add(row)
    session.flush()
    session.refresh(row)  # company_keys come from a database trigger
    return row
