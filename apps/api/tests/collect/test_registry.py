import pytest

from news_insight.collect.crawler import CrawlerCollector
from news_insight.collect.feed import FeedCollector
from news_insight.collect.json_api import JsonApiCollector
from news_insight.collect.registry import SUPPORTED_METHODS, collector_for
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod


def test_supported_methods_map_to_collectors() -> None:
    with SafeFetcher() as fetcher:
        assert isinstance(collector_for(AccessMethod.FEED, fetcher), FeedCollector)
        assert isinstance(collector_for(AccessMethod.JSON_API, fetcher), JsonApiCollector)
        assert isinstance(collector_for(AccessMethod.CRAWLER, fetcher), CrawlerCollector)
    assert set(SUPPORTED_METHODS) == {
        AccessMethod.FEED,
        AccessMethod.JSON_API,
        AccessMethod.CRAWLER,
    }


def test_unsupported_methods_are_rejected() -> None:
    with SafeFetcher() as fetcher, pytest.raises(ValueError, match="Phase 3"):
        collector_for(AccessMethod.GITHUB, fetcher)
