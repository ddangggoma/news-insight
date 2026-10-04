"""Access method → collector. JSON-shaped APIs share JsonApiCollector via presets."""

from news_insight.collect.contracts import Collector
from news_insight.collect.crawler import CrawlerCollector
from news_insight.collect.feed import FeedCollector
from news_insight.collect.json_api import JsonApiCollector
from news_insight.collect.sitemap import SitemapCollector
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod

JSON_METHODS = frozenset(
    {
        AccessMethod.JSON_API,
        AccessMethod.GITHUB,
        AccessMethod.ATPROTO,
        AccessMethod.ACTIVITYPUB,
        AccessMethod.RESEARCH_API,
    }
)
SUPPORTED_METHODS = frozenset(
    {AccessMethod.FEED, AccessMethod.CRAWLER, AccessMethod.SITEMAP} | JSON_METHODS
)


def collector_for(method: AccessMethod, fetcher: SafeFetcher) -> Collector:
    if method is AccessMethod.FEED:
        return FeedCollector(fetcher)
    if method is AccessMethod.CRAWLER:
        return CrawlerCollector(fetcher)
    if method is AccessMethod.SITEMAP:
        return SitemapCollector(fetcher)
    if method in JSON_METHODS:
        return JsonApiCollector(fetcher)
    raise ValueError(f"no collector for access method '{method.value}'")
