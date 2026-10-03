"""Active-source portfolio quotas: per-track targets and per-region capacity (roadmap D2)."""

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.sources.enums import Region, SourceStatus, Track, ValidationStage
from news_insight.sources.ladder import CheckResult
from news_insight.sources.models import Source

TRACK_TARGETS: dict[Track, int] = {
    Track.NEWS: 100,
    Track.COMMUNITY: 100,
    Track.RESEARCH_IP: 35,
    Track.OSS: 25,
}
TOTAL_TARGET = sum(TRACK_TARGETS.values())
REGION_FLOORS: dict[Region, float] = {
    Region.KR: 0.25,
    Region.GLOBAL_EN: 0.45,
    Region.JP: 0.10,
    Region.GREATER_CHINA: 0.08,
    Region.EU_OTHER: 0.12,
}


def region_capacity(region: Region) -> int:
    return math.floor(REGION_FLOORS[region] * TOTAL_TARGET + 0.5)


@dataclass(frozen=True)
class PortfolioReport:
    track_counts: dict[Track, int]
    region_counts: dict[Region, int]
    total: int

    def track_gap(self, track: Track) -> int:
        return max(TRACK_TARGETS[track] - self.track_counts[track], 0)

    def region_share(self, region: Region) -> float:
        return self.region_counts[region] / self.total if self.total else 0.0

    def region_shortfalls(self) -> dict[Region, float]:
        return {
            region: round(floor - self.region_share(region), 4)
            for region, floor in REGION_FLOORS.items()
            if self.region_share(region) < floor
        }


def build_report(pairs: Iterable[tuple[Track, Region]]) -> PortfolioReport:
    items = list(pairs)
    tracks = Counter(track for track, _ in items)
    regions = Counter(region for _, region in items)
    return PortfolioReport(
        track_counts={track: tracks.get(track, 0) for track in Track},
        region_counts={region: regions.get(region, 0) for region in Region},
        total=len(items),
    )


def active_portfolio(session: Session) -> list[tuple[Track, Region]]:
    rows = session.execute(
        select(Source.track, Source.region).where(
            Source.status == SourceStatus.ACTIVE, Source.validation_stage == ValidationStage.V6
        )
    )
    return [(track, region) for track, region in rows]


def check_quota(
    active: Sequence[tuple[Track, Region]], *, track: Track, region: Region
) -> CheckResult:
    """V6 portfolio gate: refuse promotion into a full track or a region at capacity."""
    report = build_report(active)
    reasons: list[str] = []
    track_active = report.track_counts[track]
    region_active = report.region_counts[region]
    if track_active >= TRACK_TARGETS[track]:
        reasons.append(f"track '{track.value}' is full ({track_active}/{TRACK_TARGETS[track]})")
    if region_active >= region_capacity(region):
        reasons.append(
            f"region '{region.value}' is at capacity ({region_active}/{region_capacity(region)})"
        )
    return CheckResult.from_reasons(
        reasons, {"track_active": track_active, "region_active": region_active}
    )
