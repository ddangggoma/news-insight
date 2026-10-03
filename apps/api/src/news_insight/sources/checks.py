"""Pure validation checks for ladder stages. They never touch the database."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from news_insight.collect.context import collect_context
from news_insight.collect.contracts import CollectorError, RawItem
from news_insight.collect.macros import expand_macros
from news_insight.collect.registry import collector_for
from news_insight.net.mime import EXPECTED_MIME, FEED_MIME
from news_insight.net.safe_fetch import FetchError, SafeFetcher
from news_insight.parsers.feed_probe import MIN_PROBE_ITEMS, probe_feed
from news_insight.secrets import SecretError, resolve_auth_headers
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
        ("url", source.config.get("url")),
        ("list_url", source.config.get("list_url")),
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
    try:
        resolve_auth_headers(source.config)
    except SecretError as exc:
        reasons.append(str(exc))
    storage = source.storage_right.value if source.storage_right else None
    return CheckResult.from_reasons(reasons, {"storage_right": storage})


def check_network(source: Source, fetcher: SafeFetcher) -> CheckResult:
    """V2: SSRF/DNS-rebinding guard, TLS, MIME and size limits via SafeFetcher."""
    try:
        response = fetcher.fetch(
            expand_macros(probe_url(source), now=datetime.now(UTC)),
            allowed_mime=EXPECTED_MIME[source.access_method],
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


def probe_items(
    items: Sequence[RawItem],
    *,
    now: datetime,
    min_items: int = MIN_PROBE_ITEMS,
    max_age_days: int = 30,
) -> CheckResult:
    cutoff = now - timedelta(days=max_age_days)
    dated = [item for item in items if item.published_at is not None]
    recent = [
        item for item in dated if item.published_at is not None and item.published_at >= cutoff
    ]
    reasons: list[str] = []
    if len(recent) < min_items:
        reasons.append(f"only {len(recent)} recent complete items (need {min_items})")
    return CheckResult.from_reasons(
        reasons, {"items": len(items), "dated": len(dated), "recent": len(recent)}
    )


def check_parser(source: Source, fetcher: SafeFetcher, *, now: datetime) -> CheckResult:
    """V3: one real collection must yield at least three recent, complete, dated items."""
    min_items = max(MIN_PROBE_ITEMS, int(source.config.get("probe_min_items", MIN_PROBE_ITEMS)))
    max_age_days = int(source.config.get("probe_max_age_days", 30))
    if source.access_method is AccessMethod.FEED:
        try:
            url = expand_macros(probe_url(source), now=now)
            response = fetcher.fetch(url, allowed_mime=FEED_MIME)
        except FetchError as exc:
            return CheckResult.from_reasons([str(exc)], {"error": exc.code})
        if response.status_code != 200:
            return CheckResult.from_reasons([f"unexpected HTTP status {response.status_code}"])
        return probe_feed(response.content, now=now, min_items=min_items, max_age_days=max_age_days)
    try:
        context = collect_context(source, now=now)
    except (SecretError, ValueError) as exc:
        return CheckResult.from_reasons([str(exc)], {"error": "config"})
    try:
        result = collector_for(source.access_method, fetcher).collect(context)
    except CollectorError as exc:
        return CheckResult.from_reasons([f"{exc.code}: {exc}"], {"error": exc.code})
    return probe_items(result.items, now=now, min_items=min_items, max_age_days=max_age_days)
