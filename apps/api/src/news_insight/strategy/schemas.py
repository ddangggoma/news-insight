"""Persona insights, strategy report and reviewer verdict, with the evidence rule (§7):
every insight or claim cites at least two published items from different stories."""

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from news_insight.digest.schemas import inline_schema
from news_insight.strategy.personas import PERSONA_KEYS, PERSONAS
from news_insight.taxonomy.catalog import FIELD_KEYS, THEME_KEYS

MIN_STORIES = 2


class Stance(BaseModel):
    """How a role reads one theme today (plan 13 B6)."""

    theme: str
    stance: Literal["opportunity", "risk", "watch"]


class PersonaInsight(BaseModel):
    key: str
    status: Literal["insight", "no_signal"]
    headline: str = Field(default="", max_length=160)
    insight: str = Field(default="", max_length=900)
    actions: list[str] = Field(default_factory=list, max_length=4)
    item_ids: list[int] = Field(default_factory=list, max_length=8)
    # how much today's articles matter to this role (0-100) and its reading of the main themes
    relevance: int = 0
    stances: list[Stance] = Field(default_factory=list)

    @field_validator("relevance", mode="before")
    @classmethod
    def _relevance(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            return 0
        try:
            return max(0, min(100, int(float(value))))
        except ValueError:
            return 0

    @field_validator("stances", mode="before")
    @classmethod
    def _stances(cls, value: object) -> list[dict[str, str]]:
        kept: list[dict[str, str]] = []
        for entry in value if isinstance(value, list) else []:
            if (
                isinstance(entry, dict)
                and entry.get("theme") in THEME_KEYS
                and entry.get("stance") in ("opportunity", "risk", "watch")
                and all(k["theme"] != entry["theme"] for k in kept)
            ):
                kept.append({"theme": entry["theme"], "stance": entry["stance"]})
        return kept[:3]


class PersonaBatch(BaseModel):
    personas: list[PersonaInsight]


class Claim(BaseModel):
    id: str = ""
    text: str = Field(min_length=1, max_length=600)
    item_ids: list[int] = Field(default_factory=list, max_length=8)


class FieldSection(BaseModel):
    """Claims grouped by technology field (taxonomy v2; there is no business axis)."""

    field: str
    summary: str = Field(max_length=800)
    claims: list[Claim] = Field(default_factory=list, max_length=6)


class RoadmapEntry(Claim):
    horizon: Literal["1y", "3y", "5y"]


class StrategyReport(BaseModel):
    summary: str = Field(min_length=1, max_length=1500)
    fields: list[FieldSection] = Field(default_factory=list)
    roadmap: list[RoadmapEntry] = Field(default_factory=list, max_length=12)
    opportunities: list[Claim] = Field(default_factory=list, max_length=8)
    risks: list[Claim] = Field(default_factory=list, max_length=8)


class ReviewIssue(BaseModel):
    claim_id: str
    kind: Literal["semiconductor_asset", "unsupported", "roadmap_inconsistent", "other"]
    note: str = Field(default="", max_length=400)


class Review(BaseModel):
    verdict: Literal["pass", "revise"]
    issues: list[ReviewIssue] = Field(default_factory=list)


PERSONA_SCHEMA = inline_schema(PersonaBatch)
REPORT_SCHEMA = inline_schema(StrategyReport)
REVIEW_SCHEMA = inline_schema(Review)
DROP_KINDS = frozenset({"semiconductor_asset", "unsupported", "roadmap_inconsistent"})


def supported(item_ids: list[int], story_of: dict[int, int]) -> list[int]:
    """Known ids only; empty unless they span at least MIN_STORIES distinct stories."""
    known = [i for i in dict.fromkeys(item_ids) if i in story_of]
    return known if len({story_of[i] for i in known}) >= MIN_STORIES else []


def validate_personas(raw: Any, story_of: dict[int, int]) -> list[PersonaInsight]:
    """One entry per persona; insights without two-story evidence become no_signal."""
    try:
        batch = PersonaBatch.model_validate(raw)
    except ValidationError:
        batch = PersonaBatch(personas=[])
    by_key = {p.key: p for p in batch.personas if p.key in PERSONA_KEYS}
    out = []
    for persona in PERSONAS:
        entry = by_key.get(persona.key) or PersonaInsight(key=persona.key, status="no_signal")
        evidence = supported(entry.item_ids, story_of)
        if entry.status == "insight" and evidence:
            out.append(entry.model_copy(update={"item_ids": evidence}))
        else:
            out.append(PersonaInsight(key=persona.key, status="no_signal"))
    return out


def number_claims(report: StrategyReport) -> list[Claim]:
    claims: list[Claim] = []
    for section in report.fields:
        for index, claim in enumerate(section.claims):
            claim.id = f"{section.field}-{index + 1}"
            claims.append(claim)
    for prefix, group in (
        ("roadmap", report.roadmap),
        ("opp", report.opportunities),
        ("risk", report.risks),
    ):
        for index, claim in enumerate(group):
            claim.id = f"{prefix}-{index + 1}"
            claims.append(claim)
    return claims


def _keep_supported[C: Claim](claims: list[C], story_of: dict[int, int]) -> list[C]:
    kept = []
    for claim in claims:
        evidence = supported(claim.item_ids, story_of)
        if evidence:
            claim.item_ids = evidence
            kept.append(claim)
    return kept


def validate_report(raw: Any, story_of: dict[int, int]) -> StrategyReport | None:
    """Drop claims lacking two-story evidence and sections for unknown fields."""
    try:
        report = StrategyReport.model_validate(raw)
    except ValidationError:
        return None
    report.fields = [s for s in report.fields if s.field in FIELD_KEYS]
    for section in report.fields:
        section.claims = _keep_supported(section.claims, story_of)
    report.roadmap = _keep_supported(report.roadmap, story_of)
    report.opportunities = _keep_supported(report.opportunities, story_of)
    report.risks = _keep_supported(report.risks, story_of)
    number_claims(report)
    return report


def apply_review(report: StrategyReport, review: Review) -> tuple[StrategyReport, int]:
    flagged = {issue.claim_id for issue in review.issues if issue.kind in DROP_KINDS}

    def keep(claims: list[Any]) -> list[Any]:
        return [c for c in claims if c.id not in flagged]

    before = len(number_claims(report))
    for section in report.fields:
        section.claims = keep(section.claims)
    report.roadmap = keep(report.roadmap)
    report.opportunities = keep(report.opportunities)
    report.risks = keep(report.risks)
    after = len(number_claims(report))
    return report, before - after


def claim_count(report: StrategyReport) -> int:
    return len(number_claims(report))
