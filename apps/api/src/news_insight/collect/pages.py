"""Shared helpers for page-based collectors (auto crawler, sitemaps).

Unseen article URLs are completed from the article page itself (title, description, date),
at most `enrich_limit` per run and only where robots.txt allows the path.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

from news_insight.collect.contracts import CollectContext, RawItem
from news_insight.collect.page_meta import extract_meta
from news_insight.content.normalize import canonical_url, stable_key
from news_insight.net.mime import HTML_MIME
from news_insight.net.safe_fetch import DEFAULT_USER_AGENT, FetchError, FetchResponse, SafeFetcher

DEFAULT_ENRICH_LIMIT = 15
ROBOTS_MIME = frozenset({"text/plain", "text/html", "application/octet-stream", ""})
ROBOTS_AGENT = DEFAULT_USER_AGENT.split("/", 1)[0]


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    # a publisher-declared title (news sitemap) beats the page's og:title; anchor text does not
    trusted_title: bool = False


def decode(response: FetchResponse) -> str:
    """Decode with the declared charset (e.g. EUC-KR portals), else the page's meta charset."""
    content_type = response.headers.get("content-type", "")
    charset = None
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip().strip('"')
    if not charset:
        head = response.content[:2048].decode("ascii", errors="ignore").lower()
        marker = head.find("charset=")
        if marker >= 0:
            charset = head[marker + 8 :].lstrip("\"' ").split('"')[0].split("'")[0].split(">")[0]
            charset = charset.strip(" /;") or None
    try:
        return response.content.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return response.content.decode("utf-8", errors="replace")


def timezone_of(config: dict[str, Any]) -> ZoneInfo:
    return ZoneInfo(str(config.get("timezone", "UTC")))


class RobotsGate:
    """Per-run robots.txt check for article URLs (one fetch per host)."""

    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher
        self._parsers: dict[str, RobotFileParser | None] = {}

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._parsers:
            self._parsers[host] = self._load(host)
        parser = self._parsers[host]
        return True if parser is None else parser.can_fetch(ROBOTS_AGENT, url)

    def _load(self, host: str) -> RobotFileParser | None:
        try:
            response = self._fetcher.fetch(f"{host}/robots.txt", allowed_mime=ROBOTS_MIME)
        except FetchError:
            parser = RobotFileParser()
            parser.parse(["User-agent: *", "Disallow: /"])  # unreachable: do not fetch pages
            return parser
        if 400 <= response.status_code < 500:
            return None
        parser = RobotFileParser()
        if response.status_code == 200:
            parser.parse(response.content.decode("utf-8", errors="replace").splitlines())
        else:
            parser.parse(["User-agent: *", "Disallow: /"])
        return parser


def complete(
    fetcher: SafeFetcher,
    candidates: list[Candidate],
    context: CollectContext,
    *,
    robots: RobotsGate | None = None,
) -> list[RawItem]:
    """Drop known URLs, fill missing fields from article pages, keep only titled items."""
    limit = int(context.config.get("enrich_limit", DEFAULT_ENRICH_LIMIT))
    tz = timezone_of(context.config)
    robots = robots or RobotsGate(fetcher)
    items: list[RawItem] = []
    seen: set[str] = set()
    for candidate in candidates:
        canonical = canonical_url(candidate.url)
        key = stable_key(canonical)
        if key in context.known_ids or key in seen:
            continue
        if len(items) >= limit:
            break
        seen.add(key)
        title, published, summary = candidate.title, candidate.published_at, candidate.summary
        if not (title and published and summary) and robots.allows(candidate.url):
            try:
                response = fetcher.fetch(candidate.url, allowed_mime=HTML_MIME)
            except FetchError:
                response = None
            if response is not None and response.status_code == 200:
                meta = extract_meta(decode(response), assume_tz=tz)
                if not (candidate.trusted_title and title):
                    title = meta.title or title
                published = published or meta.published_at
                summary = summary or meta.description
        if title:
            items.append(
                RawItem(
                    stable_id=canonical,
                    url=candidate.url,
                    title=title,
                    published_at=published,
                    summary=summary,
                )
            )
    return items
