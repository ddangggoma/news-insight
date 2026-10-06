"""Weekly and monthly briefing content (Claude structured output) with evidence validation."""

from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

TRAJECTORY = ("new", "rising", "steady", "fading", "reversal")


def _lines(value: object, *, limit: int, width: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:width] for v in value if str(v).strip()][:limit]


class PeriodTrend(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=900)
    item_ids: list[int] = Field(min_length=2, max_length=12)
    # across the period's days: first seen, growing, holding, quieting, turning around
    trajectory: str = "steady"
    companies: list[str] = Field(default_factory=list)

    @field_validator("trajectory", mode="before")
    @classmethod
    def _trajectory(cls, value: object) -> str:
        return value if isinstance(value, str) and value in TRAJECTORY else "steady"

    @field_validator("companies", mode="before")
    @classmethod
    def _companies(cls, value: object) -> list[str]:
        return list(dict.fromkeys(_lines(value, limit=5, width=80)))


class PeriodCompany(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=400)
    item_ids: list[int] = Field(min_length=1, max_length=6)


class PeriodicContent(BaseModel):
    headline: str = Field(min_length=1, max_length=160)
    tldr: list[str] = Field(default_factory=list)
    overview: str = Field(min_length=1, max_length=1500)
    trends: list[PeriodTrend] = Field(default_factory=list, max_length=8)
    companies: list[PeriodCompany] = Field(default_factory=list, max_length=8)
    # what a technology-strategy sensing analyst should watch and do next period
    watch_next: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)

    @field_validator("tldr", mode="before")
    @classmethod
    def _tldr(cls, value: object) -> list[str]:
        return _lines(value, limit=3, width=160)

    @field_validator("watch_next", "actions", mode="before")
    @classmethod
    def _bullets(cls, value: object) -> list[str]:
        return _lines(value, limit=5, width=200)


def validate_periodic(raw: dict[str, Any], *, known_ids: set[int]) -> PeriodicContent | None:
    """Keep only claims whose evidence ids were in the input; None if no trend survives."""
    try:
        parsed = PeriodicContent.model_validate(raw)
    except ValidationError:
        return None
    for trend in parsed.trends:
        trend.item_ids = sorted({i for i in trend.item_ids if i in known_ids})
    parsed.trends = [trend for trend in parsed.trends if len(trend.item_ids) >= 2]
    for company in parsed.companies:
        company.item_ids = sorted({i for i in company.item_ids if i in known_ids})
    parsed.companies = [company for company in parsed.companies if company.item_ids]
    return parsed if parsed.trends else None


def referenced_ids(content: PeriodicContent) -> set[int]:
    ids = {i for trend in content.trends for i in trend.item_ids}
    ids.update(i for company in content.companies for i in company.item_ids)
    return ids
