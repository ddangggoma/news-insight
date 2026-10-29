"""RSS/Atom collector with conditional GET (ETag / Last-Modified)."""

from datetime import UTC, datetime, tzinfo
from typing import Any

import feedparser

from news_insight.collect.contracts import (
    CollectContext,
    CollectorError,
    CollectResult,
    RawItem,
    majority_incomplete,
)
from news_insight.collect.fields import parse_datetime
from news_insight.collect.http import fetch_checked, request_headers
from news_insight.collect.macros import expand_macros
from news_insight.collect.pages import timezone_of
from news_insight.net.mime import FEED_MIME, HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.parsers.feed_probe import struct_to_datetime

# Some servers label a valid feed text/html (krebsonsecurity.com/feed/, 2026-10-29); the body
# decides then, and a consent or maintenance page is still refused as a wrong content type.
SNIFFED_MIME = FEED_MIME | HTML_MIME | frozenset({"text/plain"})
FEED_ROOTS = (b"<rss", b"<feed", b"<rdf:rdf")


def looks_like_feed(content: bytes) -> bool:
    """An XML document whose root is a feed (an XHTML page also starts with <?xml)."""
    head = content[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith(FEED_ROOTS):
        return True
    return head.startswith(b"<?xml") and any(root in head for root in FEED_ROOTS)


class FeedCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        url = expand_macros(context.endpoint_url, now=context.now)
        response = fetch_checked(
            self._fetcher, url, allowed_mime=SNIFFED_MIME, headers=request_headers(context)
        )
        if (
            response.status_code == 200
            and response.content_type not in FEED_MIME
            and not looks_like_feed(response.content)
        ):
            raise CollectorError(
                "blocked_mime",
                f"unexpected content type '{response.content_type}'",
                retryable=False,
            )
        if response.status_code == 304:
            return CollectResult(
                items=[],
                status_code=304,
                elapsed_ms=response.elapsed_ms,
                etag=context.etag,
                last_modified=context.last_modified,
                not_modified=True,
            )
        parsed = feedparser.parse(response.content)
        if not parsed.entries and parsed.get("bozo"):
            detail = parsed.get("bozo_exception")
            raise CollectorError("parse_error", f"unparseable feed: {detail}", retryable=False)
        window = parsed.entries[: context.item_limit]
        tz = timezone_of(context.config)
        items = [raw for entry in window if (raw := _to_item(entry, tz)) is not None]
        incomplete = len(window) - len(items)
        if majority_incomplete(incomplete, len(window)):
            raise CollectorError(
                "selector_drift",
                f"{incomplete}/{len(window)} feed entries lack id, link or title",
                retryable=False,
            )
        return CollectResult(
            items=items,
            status_code=200,
            elapsed_ms=response.elapsed_ms,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            incomplete=incomplete,
        )


def entry_date(entry: Any, tz: tzinfo) -> datetime | None:
    """The entry's date in the source's zone when the feed writes none: feedparser reads
    "2026-10-27 08:09:31" (Korean and Chinese CMSs) as UTC, nine hours late for Seoul."""
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw and (parsed := parse_datetime(raw, assume_tz=tz)) is not None:
            return parsed
    return struct_to_datetime(entry.get("published_parsed") or entry.get("updated_parsed"))


def _to_item(entry: Any, tz: tzinfo = UTC) -> RawItem | None:
    url = str(entry.get("link") or "").strip()
    stable_id = str(entry.get("id") or url).strip()
    title = str(entry.get("title") or "").strip()
    if not (url and stable_id and title):
        return None
    contents = entry.get("content") or []
    body = str(contents[0].get("value") or "") if contents else ""
    return RawItem(
        stable_id=stable_id,
        url=url,
        title=title,
        published_at=entry_date(entry, tz),
        author=str(entry.get("author") or "") or None,
        summary=str(entry.get("summary") or "") or None,
        body=body or None,
    )
