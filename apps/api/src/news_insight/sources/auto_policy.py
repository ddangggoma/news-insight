"""V1 auto-approval for public feeds and official APIs (roadmap D17).

A source without a reviewed `terms_url` may pass V1 automatically when:
- it uses a syndication or official API channel (never the HTML crawler),
- the host's robots.txt does not disallow the endpoint for our user agent
  (a missing robots.txt allows; an unreachable or failing one does not),
- any referenced credential is configured.
Auto-approved sources keep at most a 500-character excerpt (`excerpt_allowed`).
"""

from datetime import UTC, datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from news_insight.collect.macros import expand_macros
from news_insight.net.safe_fetch import DEFAULT_USER_AGENT, FetchError, SafeFetcher
from news_insight.secrets import SecretError, resolve_auth_headers
from news_insight.sources.enums import AccessMethod, StorageRight
from news_insight.sources.ladder import CheckResult
from news_insight.sources.models import Source

AUTO_APPROVABLE = frozenset(
    {
        AccessMethod.FEED,
        AccessMethod.JSON_API,
        AccessMethod.RESEARCH_API,
        AccessMethod.GITHUB,
        AccessMethod.ATPROTO,
        AccessMethod.ACTIVITYPUB,
    }
)
AUTO_STORAGE_RIGHT = StorageRight.EXCERPT_ALLOWED
ROBOTS_MIME = frozenset({"text/plain", "text/html", "application/octet-stream", ""})
ROBOTS_AGENT = DEFAULT_USER_AGENT.split("/", 1)[0]


def robots_verdict(fetcher: SafeFetcher, url: str) -> tuple[bool, str]:
    """(allowed, evidence). 4xx means no rules; 5xx or network failure means not allowed."""
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        response = fetcher.fetch(robots_url, allowed_mime=ROBOTS_MIME)
    except FetchError as exc:
        return False, f"robots.txt unavailable ({exc.code}): {robots_url}"
    if 400 <= response.status_code < 500:
        return True, f"no robots.txt ({response.status_code}): {robots_url}"
    if response.status_code != 200:
        return False, f"robots.txt returned {response.status_code}: {robots_url}"
    parser = RobotFileParser()
    parser.parse(response.content.decode("utf-8", errors="replace").splitlines())
    if parser.can_fetch(ROBOTS_AGENT, url):
        return True, f"robots.txt allows {parts.path or '/'}"
    return False, f"robots.txt disallows {parts.path or '/'} for {ROBOTS_AGENT}"


def check_auto_policy(source: Source, fetcher: SafeFetcher) -> CheckResult:
    reasons: list[str] = []
    metrics: dict[str, object] = {"auto_approved": False}
    if source.access_method not in AUTO_APPROVABLE:
        reasons.append(
            f"{source.access_method.value} sources need a manual terms review (terms_url)"
        )
        return CheckResult.from_reasons(reasons, metrics)
    if source.config.get("manual_review") is True:
        reasons.append("config.manual_review=true: terms_url review required")
        return CheckResult.from_reasons(reasons, metrics)
    endpoint = expand_macros(source.endpoint_url, now=datetime.now(UTC))
    allowed, evidence = robots_verdict(fetcher, endpoint)
    metrics["robots"] = evidence
    if not allowed:
        reasons.append(evidence)
    try:
        resolve_auth_headers(source.config)
    except SecretError as exc:
        reasons.append(str(exc))
    storage = source.storage_right or AUTO_STORAGE_RIGHT
    if storage not in (StorageRight.METADATA_ONLY, StorageRight.EXCERPT_ALLOWED):
        reasons.append("auto-approval allows at most excerpt storage; review terms for full text")
    metrics.update({"auto_approved": not reasons, "storage_right": storage.value})
    return CheckResult.from_reasons(reasons, metrics)
