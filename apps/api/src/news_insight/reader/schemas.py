"""Public reader models (§9): no operational fields (costs, errors, engines, source keys)."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from news_insight.digest.schemas import DigestItemRef, Insight


class ReaderCard(BaseModel):
    id: int
    title: str
    title_ko: str | None
    summary_ko: list[str]
    keywords: list[str]
    url: str
    source_name: str
    track: str
    category: str
    region: str
    published_at: datetime | None
    first_seen_at: datetime
    field: str | None
    themes: list[str]
    businesses: list[str]
    impact: str | None
    relevance: int | None
    coverage: int | None  # distinct publishers covering the same story


class ReaderSection(BaseModel):
    track: str
    summary: str | None
    items: list[ReaderCard]


class ReaderPersona(BaseModel):
    key: str
    name: str
    group: str
    status: str
    headline: str
    insight: str
    actions: list[str]
    item_ids: list[int]


class ReaderStrategy(BaseModel):
    personas: list[ReaderPersona]
    report: dict[str, Any] | None
    review_verdict: str | None
    dropped_claims: int


class ReaderBriefing(BaseModel):
    briefing_date: date
    version: int
    published_at: datetime
    headline: str | None
    overview: str | None
    insights: list[Insight]
    sections: list[ReaderSection]
    strategy: ReaderStrategy | None
    refs: list[DigestItemRef]
    gates_passed: int
    gates_total: int
    previous_date: date | None
    next_date: date | None


class ArchiveEntry(BaseModel):
    briefing_date: date
    version: int
    headline: str | None
    items: int
    published_at: datetime


class TaxonomyCounts(BaseModel):
    window_days: int
    total: int
    fields: dict[str, int]
    themes: dict[str, int]
    businesses: dict[str, int]
    impacts: dict[str, int]


class ReaderPage(BaseModel):
    items: list[ReaderCard]
    total: int
    page: int
    size: int


class ArchivePage(BaseModel):
    items: list[ArchiveEntry]
    total: int
    page: int
    size: int
