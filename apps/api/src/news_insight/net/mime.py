"""Content types each access method may return; shared by V2 checks and collectors."""

from news_insight.sources.enums import AccessMethod

FEED_MIME = frozenset(
    {
        "application/rss+xml",
        "application/atom+xml",
        "application/rdf+xml",
        "application/xml",
        "text/xml",
    }
)
JSON_MIME = frozenset({"application/json", "application/activity+json", "application/ld+json"})
HTML_MIME = frozenset({"text/html", "application/xhtml+xml"})
EXPECTED_MIME: dict[AccessMethod, frozenset[str]] = {
    AccessMethod.FEED: FEED_MIME,
    AccessMethod.JSON_API: JSON_MIME,
    AccessMethod.CRAWLER: HTML_MIME,
    AccessMethod.GITHUB: JSON_MIME,
    AccessMethod.ATPROTO: JSON_MIME,
    AccessMethod.ACTIVITYPUB: JSON_MIME,
    AccessMethod.RESEARCH_API: JSON_MIME | FEED_MIME,
}
