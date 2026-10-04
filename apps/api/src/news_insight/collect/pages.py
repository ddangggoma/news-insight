"""Shared helpers for page-based collectors (auto crawler, sitemaps).

Unseen article URLs are completed from the article page itself (title, description, date),
at most `enrich_limit` per run and only where robots.txt allows the path.
"""

import re
from dataclasses import dataclass, replace
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
    """Drop known URLs, fill missing fields from article pages, keep only titled items.

    - a page that was fetched but carries no publication date is not an article (category
      and list pages) unless `config.date_fallback: now` (boards that print no date meta),
    - an og:title shared by several pages is the site name, so the anchor text wins.
    """
    limit = int(context.config.get("enrich_limit", DEFAULT_ENRICH_LIMIT))
    now_fallback = context.config.get("date_fallback") == "now"
    tz = timezone_of(context.config)
    robots = robots or RobotsGate(fetcher)
    kept: list[tuple[Candidate, str | None, RawItem]] = []
    page_titles: dict[str, int] = {}
    seen: set[str] = set()
    for candidate in candidates:
        canonical = canonical_url(candidate.url)
        key = stable_key(canonical)
        if key in context.known_ids or key in seen:
            continue
        if len(kept) >= limit:
            break
        seen.add(key)
        title, published, summary = candidate.title, candidate.published_at, candidate.summary
        page_title: str | None = None
        fetched = False
        if not (title and published and summary) and robots.allows(candidate.url):
            try:
                response = fetcher.fetch(candidate.url, allowed_mime=HTML_MIME)
            except FetchError:
                response = None
            if response is not None and response.status_code == 200:
                fetched = True
                meta = extract_meta(decode(response), assume_tz=tz)
                page_title = meta.title
                if page_title:
                    page_titles[page_title] = page_titles.get(page_title, 0) + 1
                published = published or meta.published_at
                summary = summary or meta.description
        if published is None:
            if now_fallback:
                published = context.now
            elif fetched:
                continue
        best = title if candidate.trusted_title and title else (page_title or title)
        if best:
            item = RawItem(
                stable_id=canonical,
                url=candidate.url,
                title=best,
                published_at=published,
                summary=summary,
            )
            kept.append((candidate, page_title, item))
    items: list[RawItem] = []
    for candidate, page_title, item in kept:
        if page_title and page_titles.get(page_title, 0) > 1 and candidate.title:
            item = replace(item, title=candidate.title)
        items.append(item)
    return strip_site_suffix(items)


SUFFIX = re.compile(r"^(?P<head>.+?)\s+(?:\||-|–|—|:|::|·)\s+(?P<tail>[^|:–—·-]{2,40})$")


def strip_site_suffix(items: list[RawItem]) -> list[RawItem]:
    """Remove a trailing ' | Site' / ' - Site' / ' : Site' shared by two or more titles."""
    tails: dict[str, int] = {}
    for item in items:
        match = SUFFIX.match(item.title)
        if match:
            tails[match["tail"]] = tails.get(match["tail"], 0) + 1
    result = []
    for item in items:
        match = SUFFIX.match(item.title)
        if match and tails.get(match["tail"], 0) > 1:
            item = replace(item, title=match["head"].strip())
        result.append(item)
    return result
