"""Response models for the operations console API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from news_insight.collect.models import FetchOutcome
from news_insight.sources.enums import (
    AccessMethod,
    PollClass,
    Region,
    SourceStatus,
    StorageRight,
    Track,
    ValidationOutcome,
    ValidationStage,
)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


class TrackCount(BaseModel):
    track: Track
    total: int
    active: int
    target: int


class RegionCount(BaseModel):
    region: Region
    total: int
    active: int
    capacity: int


class StageCount(BaseModel):
    stage: ValidationStage
    count: int


class Health(BaseModel):
    window_hours: int
    runs: int
    success: int
    not_modified: int
    failed: int
    dead_lettered: int
    skipped: int
    items_new: int
    paused_sources: int
    open_dead_letters: int


class Overview(BaseModel):
    generated_at: datetime
    tracks: list[TrackCount]
    regions: list[RegionCount]
    stages: list[StageCount]
    health: Health


class SourceRow(BaseModel):
    key: str
    name: str
    track: Track
    category: str
    region: Region
    access_method: AccessMethod
    validation_stage: ValidationStage
    status: SourceStatus
    paused_reason: str | None
    next_due_at: datetime | None
    interval_seconds: int | None
    consecutive_failures: int
    last_success_at: datetime | None
    items_total: int


class ValidationEventOut(BaseModel):
    stage: ValidationStage
    outcome: ValidationOutcome
    reasons: list[str]
    created_at: datetime


class RunOut(BaseModel):
    id: int
    source_key: str
    started_at: datetime
    outcome: FetchOutcome
    http_status: int | None
    elapsed_ms: int | None
    items_new: int
    items_updated: int
    items_unchanged: int
    error_code: str | None
    error_message: str | None
    canary: bool


class ItemRow(BaseModel):
    id: int
    title: str
    url: str
    source_key: str
    source_name: str
    track: Track
    category: str
    region: Region
    published_at: datetime | None
    first_seen_at: datetime
    revision: int
    canary: bool
    metrics: dict[str, int]
    title_ko: str | None = None


class CardBody(BaseModel):
    title_ko: str | None
    summary_ko: list[str]
    keywords: list[str]
    status: str
    engine: str | None
    model: str | None
    generated_at: datetime


class CardView(BaseModel):
    item: ItemRow
    card: CardBody


class CardRunOut(BaseModel):
    started_at: datetime
    finished_at: datetime | None
    ready: int
    failed: int
    batches: dict[str, int]
    quota: dict[str, int | None]
    note: str | None


class CardStats(BaseModel):
    ready: int
    failed: int
    pending: int
    ready_today: int
    by_engine: dict[str, int]
    last_run: CardRunOut | None


class SourceDetail(BaseModel):
    source: SourceRow
    endpoint_url: str
    official_domain: str
    operator: str
    language: str
    poll_class: PollClass
    dx_relevance: str
    terms_url: str | None
    storage_right: StorageRight | None
    config: dict[str, Any]
    events: list[ValidationEventOut]
    runs: list[RunOut]
    items: list[ItemRow]


class DeadLetterOut(BaseModel):
    id: int
    source_key: str
    error_code: str
    error_message: str
    attempts: int
    created_at: datetime
    resolved_at: datetime | None
    resolution: str | None


class RevisionOut(BaseModel):
    revision: int
    title: str
    recorded_at: datetime


class MetricPoint(BaseModel):
    captured_at: datetime
    metrics: dict[str, int]


class ItemDetail(BaseModel):
    item: ItemRow
    summary: str | None
    body: str | None
    author: str | None
    revisions: list[RevisionOut]
    metric_history: list[MetricPoint]
    card: CardBody | None = None


class MoverOut(BaseModel):
    item: ItemRow
    current: int
    baseline: int
    delta: int


class PauseBody(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class Queued(BaseModel):
    queued: bool
