"""XML sitemap collector. Google News sitemaps give titles and dates directly; plain
sitemaps give URLs and lastmod, completed from article pages (pages.complete)."""

import re
import xml.etree.ElementTree as ET
from datetime import datetime

from news_insight.collect.contracts import CollectContext, CollectorError, CollectResult
from news_insight.collect.fields import parse_datetime
from news_insight.collect.http import fetch_checked
from news_insight.collect.macros import expand_macros
from news_insight.collect.pages import Candidate, RobotsGate, complete, timezone_of
from news_insight.content.normalize import clean_text
from news_insight.net.mime import EXPECTED_MIME
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import AccessMethod

SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
NEWS = "{http://www.google.com/schemas/sitemap-news/0.9}"
MIME = EXPECTED_MIME[AccessMethod.SITEMAP]
MAX_CHILDREN = 2


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, *names: str) -> str | None:
    for name in names:
        found = node.find(name)
        if found is not None and found.text and found.text.strip():
            return found.text.strip()
    return None


def _parse(content: bytes) -> ET.Element:
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise CollectorError("parse_error", f"sitemap is not XML: {exc}", retryable=False) from exc


def _pick_children(root: ET.Element) -> list[str]:
    entries: list[tuple[str, str]] = []
    for node in root.findall(f"{SM}sitemap"):
        loc = _child_text(node, f"{SM}loc")
        if loc and not loc.endswith(".gz"):
            entries.append((loc, _child_text(node, f"{SM}lastmod") or ""))
    news = [loc for loc, _ in entries if "news" in loc.lower()]
    if news:
        return news[:MAX_CHILDREN]
    entries.sort(key=lambda entry: entry[1], reverse=True)
    if entries and not entries[0][1]:
        return [loc for loc, _ in entries[-MAX_CHILDREN:]]  # undated indexes list oldest first
    return [loc for loc, _ in entries[:MAX_CHILDREN]]


def _candidates(
    root: ET.Element, context: CollectContext, pattern: re.Pattern[str] | None
) -> list[Candidate]:
    tz = timezone_of(context.config)
    rows: list[tuple[datetime | None, Candidate]] = []
    for node in root.findall(f"{SM}url"):
        loc = _child_text(node, f"{SM}loc")
        if not loc or (pattern is not None and not pattern.search(loc)):
            continue
        news = node.find(f"{NEWS}news")
        title = _child_text(news, f"{NEWS}title") if news is not None else None
        raw_date = (
            _child_text(news, f"{NEWS}publication_date") if news is not None else None
        ) or _child_text(node, f"{SM}lastmod")
        published = parse_datetime(raw_date, assume_tz=tz) if raw_date else None
        rows.append(
            (
                published,
                Candidate(
                    url=loc,
                    title=clean_text(title),
                    published_at=published,
                    trusted_title=bool(title),
                ),
            )
        )
    rows.sort(key=lambda row: row[0].timestamp() if row[0] else 0.0, reverse=True)
    return [candidate for _, candidate in rows]


class SitemapCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        url = expand_macros(context.endpoint_url, now=context.now)
        response = fetch_checked(self._fetcher, url, allowed_mime=MIME, headers=context.headers)
        elapsed = response.elapsed_ms
        root = _parse(response.content)
        if _local(root.tag) == "sitemapindex":
            children = _pick_children(root)
            if not children:
                raise CollectorError(
                    "parse_error", "sitemap index lists no sitemaps", retryable=False
                )
            urlsets = []
            for child in children:
                child_response = fetch_checked(
                    self._fetcher, child, allowed_mime=MIME, headers=context.headers
                )
                elapsed += child_response.elapsed_ms
                urlsets.append(_parse(child_response.content))
        else:
            urlsets = [root]
        pattern_text = context.config.get("link_pattern")
        pattern = re.compile(str(pattern_text)) if pattern_text else None
        candidates = [c for urlset in urlsets for c in _candidates(urlset, context, pattern)]
        if not candidates:
            raise CollectorError("selector_drift", "sitemap has no matching URLs", retryable=False)
        items = complete(self._fetcher, candidates, context, robots=RobotsGate(self._fetcher))
        return CollectResult(items=items, status_code=200, elapsed_ms=elapsed)
