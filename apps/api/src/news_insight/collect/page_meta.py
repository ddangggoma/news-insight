"""Article metadata from an HTML page: title, description and publication time.

Order of trust: Open Graph / article meta → JSON-LD → <time> → <title>/<h1>.
Used to complete items found by the auto crawler and by sitemaps without news titles.
"""

import json
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any

from selectolax.parser import HTMLParser

from news_insight.collect.fields import parse_datetime
from news_insight.content.normalize import clean_text

TITLE_META = (
    'meta[property="og:title"]',
    'meta[name="twitter:title"]',
    'meta[name="title"]',
)
DESCRIPTION_META = (
    'meta[property="og:description"]',
    'meta[name="description"]',
    'meta[name="twitter:description"]',
)
DATE_META = (
    'meta[property="article:published_time"]',
    'meta[name="article:published_time"]',
    'meta[property="og:article:published_time"]',
    'meta[itemprop="datePublished"]',
    'meta[name="pubdate"]',
    'meta[name="publishdate"]',
    'meta[name="publish-date"]',
    'meta[name="date"]',
    'meta[name="parsely-pub-date"]',
    'meta[name="sailthru.date"]',
    'meta[name="DC.date.issued"]',
    'meta[name="dc.date"]',
    'meta[property="og:regDate"]',
)
LD_TYPES = ("article", "newsarticle", "blogposting", "reportagenewsarticle", "techarticle")


@dataclass(frozen=True)
class PageMeta:
    title: str | None
    description: str | None
    published_at: datetime | None


def _first_meta(tree: HTMLParser, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        node = tree.css_first(selector)
        if node is not None:
            value = (node.attributes.get("content") or "").strip()
            if value:
                return value
    return None


def _ld_objects(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [obj for item in value for obj in _ld_objects(item)]
    if isinstance(value, dict):
        nested = value.get("@graph")
        return [value, *_ld_objects(nested)] if nested else [value]
    return []


def _ld_article(tree: HTMLParser) -> dict[str, Any] | None:
    for script in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.text() or "")
        except ValueError:
            continue
        for obj in _ld_objects(data):
            kind = obj.get("@type")
            kinds = [kind] if isinstance(kind, str) else kind if isinstance(kind, list) else []
            if any(str(k).lower() in LD_TYPES for k in kinds):
                return obj
    return None


def extract_meta(html: str, *, assume_tz: tzinfo) -> PageMeta:
    tree = HTMLParser(html)
    article = _ld_article(tree) or {}
    title = _first_meta(tree, TITLE_META) or str(article.get("headline") or "") or None
    if not title:
        h1 = tree.css_first("h1")
        title_node = tree.css_first("title")
        title = (h1.text() if h1 is not None else None) or (
            title_node.text() if title_node is not None else None
        )
    description = _first_meta(tree, DESCRIPTION_META) or str(article.get("description") or "")
    raw_date: Any = _first_meta(tree, DATE_META) or article.get("datePublished")
    if not raw_date:
        time_node = tree.css_first("time[datetime]")
        raw_date = time_node.attributes.get("datetime") if time_node is not None else None
    return PageMeta(
        title=clean_text(title, limit=300) if title else None,
        description=clean_text(description) if description else None,
        published_at=parse_datetime(raw_date, assume_tz=assume_tz) if raw_date else None,
    )
