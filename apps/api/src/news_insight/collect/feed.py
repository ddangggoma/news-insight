"""RSS/Atom collector with conditional GET (ETag / Last-Modified)."""

from dataclasses import replace
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
from news_insight.collect.page_meta import publication_dates
from news_insight.collect.pages import DEFAULT_ENRICH_LIMIT, RobotsGate, decode, timezone_of
from news_insight.content.dates import page_date
from news_insight.content.normalize import stable_key
from news_insight.net.mime import FEED_MIME, HTML_MIME
from news_insight.net.safe_fetch import FetchError, SafeFetcher
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


MAX_FEED_BYTES = 20 * 1024 * 1024


def _max_bytes(config: dict[str, Any]) -> int | None:
    """A source's own size limit (`max_bytes`), up to 20 MB; None keeps the fetcher's."""
    try:
        value = int(config.get("max_bytes") or 0)
    except (TypeError, ValueError):
        return None
    return min(value, MAX_FEED_BYTES) if value > 0 else None


class FeedCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        url = expand_macros(context.endpoint_url, now=context.now)
        response = fetch_checked(
            self._fetcher,
            url,
            allowed_mime=SNIFFED_MIME,
            headers=request_headers(context),
            max_bytes=_max_bytes(context.config),
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
        local_clock = bool(context.config.get("local_clock"))
        items = [raw for entry in window if (raw := _to_item(entry, tz, local_clock)) is not None]
        incomplete = len(window) - len(items)
        if context.config.get("page_date"):
            items = self._with_page_dates(items, context, tz)
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

    def _with_page_dates(
        self, items: list[RawItem], context: CollectContext, tz: tzinfo
    ) -> list[RawItem]:
        """`config.page_date`: feeds that list an old post again under a new date (an evergreen
        guide refreshed, a gov.uk "last updated", a blog moved to a new address) give the
        publication date its article page states, when that is earlier and the page agrees
        with itself. Only new entries are read, `enrich_limit` of them per run."""
        limit = int(context.config.get("enrich_limit", DEFAULT_ENRICH_LIMIT))
        robots = RobotsGate(self._fetcher)
        fresh = [item for item in items if stable_key(item.stable_id) not in context.known_ids]
        dated: dict[str, datetime] = {}
        for item in fresh[:limit]:
            if not robots.allows(item.url):
                continue
            try:
                response = self._fetcher.fetch(item.url, allowed_mime=HTML_MIME)
            except FetchError:
                continue
            if response.status_code != 200:
                continue
            truth = page_date(
                item.published_at,
                publication_dates(decode(response), assume_tz=tz),
                seen=context.now,
                tz=tz,
                offset_only=False,
            )
            if truth is not None:
                dated[item.stable_id] = truth
        return [
            replace(item, published_at=dated[item.stable_id]) if item.stable_id in dated else item
            for item in items
        ]


def entry_date(entry: Any, tz: tzinfo, local_clock: bool = False) -> datetime | None:
    """The entry's date in the source's zone when the feed writes none: feedparser reads
    "2026-10-27 08:09:31" (Korean and Chinese CMSs) as UTC, nine hours late for Seoul.

    `local_clock` (`config.local_clock`): the feed writes the source's wall clock but labels it
    "+0000" (Samsung Newsroom: "08:00:00 +0000" for a page that says 08:00+09:00), so the label
    is dropped and the wall clock read in the source's zone."""
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw and (parsed := parse_datetime(raw, assume_tz=tz)) is not None:
            return parsed.replace(tzinfo=tz).astimezone(UTC) if local_clock else parsed
    return struct_to_datetime(entry.get("published_parsed") or entry.get("updated_parsed"))


def _to_item(entry: Any, tz: tzinfo = UTC, local_clock: bool = False) -> RawItem | None:
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
        published_at=entry_date(entry, tz, local_clock),
        author=str(entry.get("author") or "") or None,
        summary=str(entry.get("summary") or "") or None,
        body=body or None,
    )
