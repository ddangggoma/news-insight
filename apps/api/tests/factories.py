from typing import Any

from news_insight.sources.enums import (
    AccessMethod,
    PollClass,
    Region,
    SourceStatus,
    StorageRight,
    Track,
    ValidationStage,
)
from news_insight.sources.models import Source


def source_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "key": "example-news",
        "name": "Example News",
        "track": Track.NEWS,
        "category": "independent_media",
        "access_method": AccessMethod.FEED,
        "endpoint_url": "https://www.example.com/feed.xml",
        "official_domain": "example.com",
        "operator": "Example Media Inc.",
        "region": Region.GLOBAL_EN,
        "language": "en",
        "poll_class": PollClass.NEWS,
        "dx_relevance": "모바일·가전·디스플레이 제품 동향을 다루는 테크 미디어",
        "terms_url": "https://www.example.com/terms",
        "storage_right": StorageRight.EXCERPT_ALLOWED,
        "config": {},
    }
    values.update(overrides)
    return values


def build_source(**overrides: Any) -> Source:
    values = {
        "validation_stage": ValidationStage.UNVERIFIED,
        "status": SourceStatus.CANDIDATE,
        **source_values(),
    }
    values.update(overrides)
    return Source(**values)
