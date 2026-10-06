"""Digest content (Claude structured output) and API views, with evidence validation."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from news_insight.digest.models import DigestStatus
from news_insight.sources.enums import Track

if TYPE_CHECKING:
    from news_insight.digest.bundle import Bundle


class DigestPoint(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    item_ids: list[int] = Field(min_length=1, max_length=8)


class CategorySection(BaseModel):
    category: str
    headline: str = Field(min_length=1, max_length=200)
    points: list[DigestPoint] = Field(max_length=5)


class TrackSection(BaseModel):
    track: Track
    summary: str = Field(min_length=1, max_length=600)
    categories: list[CategorySection]


CONTINUITY = ("new", "continuing", "escalation", "reversal")


class Insight(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=800)
    item_ids: list[int] = Field(min_length=2, max_length=10)
    # against the last three briefings (plan 13 B1): new, still going, growing, turning around
    continuity: str = "new"
    previous_title: str | None = None
    # registered company names the insight is about (plan 12)
    companies: list[str] = Field(default_factory=list)

    @field_validator("continuity", mode="before")
    @classmethod
    def _continuity(cls, value: object) -> str:
        return value if isinstance(value, str) and value in CONTINUITY else "new"

    @field_validator("previous_title", mode="before")
    @classmethod
    def _previous(cls, value: object) -> str | None:
        return str(value).strip()[:120] or None if value else None

    @field_validator("companies", mode="before")
    @classmethod
    def _companies(cls, value: object) -> list[str]:
        names = (
            [str(v).strip()[:80] for v in value or [] if str(v).strip()]
            if isinstance(value, list)
            else []
        )
        return list(dict.fromkeys(names))[:5]


class DigestContent(BaseModel):
    headline: str = Field(min_length=1, max_length=160)
    # three lines a reader can take away in a minute (plan 13 C1)
    tldr: list[str] = Field(default_factory=list)
    overview: str = Field(min_length=1, max_length=1200)
    tracks: list[TrackSection]
    insights: list[Insight] = Field(max_length=8)

    @field_validator("tldr", mode="before")
    @classmethod
    def _tldr(cls, value: object) -> list[str]:
        lines = (
            [str(v).strip()[:160] for v in value or [] if str(v).strip()]
            if isinstance(value, list)
            else []
        )
        return lines[:3]


class DigestItemRef(BaseModel):
    id: int
    title: str
    url: str
    source_name: str
    track: Track


class DigestOut(BaseModel):
    digest_date: date
    version: int
    status: DigestStatus
    model: str | None
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    item_count: int
    cost_usd: float | None
    error: str | None
    content: DigestContent
    items: list[DigestItemRef]


class DigestSummary(BaseModel):
    digest_date: date
    version: int
    status: DigestStatus
    headline: str
    item_count: int
    generated_at: datetime


def validate_content(raw: dict[str, Any], *, known_ids: set[int]) -> DigestContent | None:
    """Keep only claims whose evidence ids exist in the input; None if nothing survives."""
    try:
        parsed = DigestContent.model_validate(raw)
    except ValidationError:
        return None
    for track in parsed.tracks:
        for category in track.categories:
            for point in category.points:
                point.item_ids = [i for i in point.item_ids if i in known_ids]
            category.points = [point for point in category.points if point.item_ids]
        track.categories = [category for category in track.categories if category.points]
    parsed.tracks = [track for track in parsed.tracks if track.categories]
    for insight in parsed.insights:
        insight.item_ids = sorted({i for i in insight.item_ids if i in known_ids})
    parsed.insights = [insight for insight in parsed.insights if len(insight.item_ids) >= 2]
    return parsed if parsed.tracks else None


def fallback_content(bundle: "Bundle", *, reason: str) -> DigestContent:
    """Rule-based digest: the top titles per track and category, no synthesized claims."""
    tracks: list[TrackSection] = []
    for section in bundle.payload.get("tracks", []):
        categories = [
            CategorySection(
                category=category["category"],
                headline=f"상위 {min(3, len(category['items']))}건",
                points=[
                    DigestPoint(text=item["title"][:400], item_ids=[item["id"]])
                    for item in category["items"][:3]
                ],
            )
            for category in section["categories"]
            if category["items"]
        ]
        if categories:
            tracks.append(
                TrackSection(
                    track=section["track"],
                    summary=(
                        f"전일 {section['item_count']}건 수집 (자동 요약 없이 상위 항목만 표시)"
                    ),
                    categories=categories,
                )
            )
    headline = (
        "자동 요약을 만들지 못해 수집 상위 항목만 정리했습니다"
        if tracks
        else "전일 수집된 항목이 없습니다"
    )
    return DigestContent(
        headline=headline,
        overview="이 다이제스트는 규칙 기반 대체본입니다. 운영 콘솔에서 생성 로그를 확인하세요.",
        tracks=tracks,
        insights=[],
    )


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with every $ref expanded (the CLI expects a self-contained schema)."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def expand(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return expand(definitions[node["$ref"].rsplit("/", 1)[-1]])
            return {key: expand(value) for key, value in node.items()}
        if isinstance(node, list):
            return [expand(value) for value in node]
        return node

    expanded: dict[str, Any] = expand(schema)
    return expanded
