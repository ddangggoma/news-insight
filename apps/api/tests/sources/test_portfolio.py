import pytest
from sqlalchemy.orm import Session

from news_insight.sources.enums import Region, SourceStatus, Track, ValidationStage
from news_insight.sources.portfolio import (
    REGION_FLOORS,
    TOTAL_TARGET,
    TRACK_TARGETS,
    active_portfolio,
    build_report,
    check_quota,
    region_capacity,
)
from tests.factories import build_source


def test_targets_match_requirements() -> None:
    assert TRACK_TARGETS == {
        Track.NEWS: 100,
        Track.COMMUNITY: 100,
        Track.RESEARCH_IP: 35,
        Track.OSS: 25,
    }
    assert TOTAL_TARGET == 260
    assert sum(REGION_FLOORS.values()) == pytest.approx(1.0)


def test_region_capacities_partition_the_total() -> None:
    capacities = {region: region_capacity(region) for region in Region}

    assert capacities == {
        Region.KR: 65,
        Region.GLOBAL_EN: 117,
        Region.JP: 26,
        Region.GREATER_CHINA: 21,
        Region.EU_OTHER: 31,
    }
    assert sum(capacities.values()) == TOTAL_TARGET


def test_report_counts_shares_and_shortfalls() -> None:
    report = build_report([(Track.NEWS, Region.KR), (Track.NEWS, Region.GLOBAL_EN)] * 2)

    assert report.total == 4
    assert report.track_counts[Track.NEWS] == 4
    assert report.track_gap(Track.NEWS) == 96
    assert report.region_share(Region.KR) == 0.5
    shortfalls = report.region_shortfalls()
    assert Region.KR not in shortfalls
    assert shortfalls[Region.JP] == pytest.approx(0.10)


def test_empty_report_has_zero_shares() -> None:
    assert build_report([]).region_share(Region.KR) == 0.0


def test_quota_blocks_full_track() -> None:
    active = [(Track.OSS, Region.GLOBAL_EN)] * 25

    result = check_quota(active, track=Track.OSS, region=Region.GLOBAL_EN)

    assert result.reasons == ["track 'oss' is full (25/25)"]


def test_quota_blocks_region_at_capacity() -> None:
    active = [(Track.NEWS, Region.GREATER_CHINA)] * 21

    result = check_quota(active, track=Track.NEWS, region=Region.GREATER_CHINA)

    assert result.reasons == ["region 'greater_china' is at capacity (21/21)"]


def test_quota_passes_with_room() -> None:
    result = check_quota([], track=Track.NEWS, region=Region.KR)

    assert result.passed
    assert result.metrics == {"track_active": 0, "region_active": 0}


@pytest.mark.db
def test_active_portfolio_only_counts_active_v6(db_session: Session) -> None:
    db_session.add_all(
        [
            build_source(
                key="live",
                validation_stage=ValidationStage.V6,
                status=SourceStatus.ACTIVE,
                region=Region.KR,
                language="ko",
            ),
            build_source(key="pending", validation_stage=ValidationStage.V3),
            build_source(
                key="paused", validation_stage=ValidationStage.V6, status=SourceStatus.PAUSED
            ),
        ]
    )
    db_session.flush()

    assert active_portfolio(db_session) == [(Track.NEWS, Region.KR)]
