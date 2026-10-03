"""Pure validation checks for ladder stages. They never touch the database."""

from urllib.parse import urlsplit

from news_insight.net.safe_fetch import FetchError, SafeFetcher
from news_insight.sources.enums import AccessMethod, Region, StorageRight, Track
from news_insight.sources.ladder import CheckResult
from news_insight.sources.models import Source

REGION_LANGUAGES: dict[Region, frozenset[str] | None] = {
    Region.KR: frozenset({"ko", "en"}),
    Region.GLOBAL_EN: frozenset({"en"}),
    Region.JP: frozenset({"ja", "en"}),
    Region.GREATER_CHINA: frozenset({"zh", "en"}),
    Region.EU_OTHER: None,
}
FULLTEXT_RIGHTS = frozenset({StorageRight.FULLTEXT_TTL, StorageRight.FULLTEXT_PERMITTED})
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
EXPECTED_MIME: dict[AccessMethod, frozenset[str]] = {
    AccessMethod.FEED: FEED_MIME,
    AccessMethod.JSON_API: JSON_MIME,
    AccessMethod.CRAWLER: frozenset({"text/html", "application/xhtml+xml"}),
    AccessMethod.GITHUB: JSON_MIME,
    AccessMethod.ATPROTO: JSON_MIME,
    AccessMethod.ACTIVITYPUB: JSON_MIME,
    AccessMethod.RESEARCH_API: JSON_MIME | FEED_MIME,
}


def probe_url(source: Source) -> str:
    return str(source.config.get("probe_url") or source.endpoint_url)


def _host_matches(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def check_identity(source: Source) -> CheckResult:
    """V0: official domain, operator, region/language and DX relevance."""
    reasons: list[str] = []
    allowed_hosts = {str(host).lower() for host in source.config.get("allowed_hosts", [])}
    endpoint_host = (urlsplit(source.endpoint_url).hostname or "").lower()
    for label, url in (
        ("endpoint", source.endpoint_url),
        ("probe", source.config.get("probe_url")),
    ):
        if not url:
            continue
        host = (urlsplit(str(url)).hostname or "").lower()
        if not (_host_matches(host, source.official_domain) or host in allowed_hosts):
            reasons.append(
                f"{label} host '{host}' is not under official domain '{source.official_domain}'"
            )
    if not source.operator.strip():
        reasons.append("operator is missing")
    if len(source.dx_relevance.strip()) < 10:
        reasons.append("dx_relevance rationale is missing or too short")
    expected = REGION_LANGUAGES[source.region]
    primary_language = source.language.split("-", 1)[0].lower()
    if expected is not None and primary_language not in expected:
        reasons.append(
            f"language '{source.language}' does not match region '{source.region.value}'"
        )
    return CheckResult.from_reasons(reasons, {"endpoint_host": endpoint_host})


def check_policy(source: Source) -> CheckResult:
    """V1: terms reviewed, storage right declared, crawler and paywall rules."""
    reasons: list[str] = []
    if not source.terms_url:
        reasons.append("terms_url is missing")
    elif urlsplit(source.terms_url).scheme != "https":
        reasons.append("terms_url must use https")
    if source.storage_right is None:
        reasons.append("storage_right is not declared")
    if source.access_method is AccessMethod.CRAWLER:
        if source.config.get("crawl_permitted") is not True:
            reasons.append("crawler requires config.crawl_permitted=true after terms review")
        if source.config.get("robots_checked") is not True:
            reasons.append("crawler requires config.robots_checked=true")
        if not source.config.get("selectors"):
            reasons.append("crawler requires declarative config.selectors")
    if (
        source.track is Track.RESEARCH_IP
        and source.storage_right in FULLTEXT_RIGHTS
        and source.config.get("open_access") is not True
    ):
        reasons.append(
            "full-text storage for research/IP requires config.open_access=true "
            "(paywall bypass is forbidden)"
        )
    storage = source.storage_right.value if source.storage_right else None
    return CheckResult.from_reasons(reasons, {"storage_right": storage})


def check_network(source: Source, fetcher: SafeFetcher) -> CheckResult:
    """V2: SSRF/DNS-rebinding guard, TLS, MIME and size limits via SafeFetcher."""
    try:
        response = fetcher.fetch(
            probe_url(source), allowed_mime=EXPECTED_MIME[source.access_method]
        )
    except FetchError as exc:
        return CheckResult.from_reasons([str(exc)], {"error": exc.code})
    reasons: list[str] = []
    if response.status_code != 200:
        reasons.append(f"unexpected HTTP status {response.status_code}")
    return CheckResult.from_reasons(
        reasons,
        {
            "status": response.status_code,
            "content_type": response.content_type,
            "bytes": len(response.content),
            "redirects": len(response.redirects),
            "elapsed_ms": response.elapsed_ms,
        },
    )
