from news_insight.collect.crawler import CrawlerCollector
from news_insight.collect.feed import FeedCollector
from news_insight.collect.json_api import JsonApiCollector
from news_insight.collect.registry import SUPPORTED_METHODS, collector_for
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod

JSON_METHODS = (
    AccessMethod.JSON_API,
    AccessMethod.GITHUB,
    AccessMethod.ATPROTO,
    AccessMethod.ACTIVITYPUB,
    AccessMethod.RESEARCH_API,
)


def test_every_access_method_has_a_collector() -> None:
    with SafeFetcher() as fetcher:
        assert isinstance(collector_for(AccessMethod.FEED, fetcher), FeedCollector)
        assert isinstance(collector_for(AccessMethod.CRAWLER, fetcher), CrawlerCollector)
        for method in JSON_METHODS:
            assert isinstance(collector_for(method, fetcher), JsonApiCollector)
    assert set(SUPPORTED_METHODS) == set(AccessMethod)
