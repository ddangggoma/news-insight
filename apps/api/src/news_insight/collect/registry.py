"""Access method → collector. GitHub, AT Protocol, ActivityPub and research APIs arrive in P3."""

from news_insight.collect.contracts import Collector
from news_insight.collect.crawler import CrawlerCollector
from news_insight.collect.feed import FeedCollector
from news_insight.collect.json_api import JsonApiCollector
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod

SUPPORTED_METHODS = frozenset({AccessMethod.FEED, AccessMethod.JSON_API, AccessMethod.CRAWLER})


def collector_for(method: AccessMethod, fetcher: SafeFetcher) -> Collector:
    if method is AccessMethod.FEED:
        return FeedCollector(fetcher)
    if method is AccessMethod.JSON_API:
        return JsonApiCollector(fetcher)
    if method is AccessMethod.CRAWLER:
        return CrawlerCollector(fetcher)
    raise ValueError(f"no collector for access method '{method.value}' yet (Phase 3)")
