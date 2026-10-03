"""RSS/Atom collector with conditional GET (ETag / Last-Modified)."""

from typing import Any

import feedparser

from news_insight.collect.contracts import (
    CollectContext,
    CollectorError,
    CollectResult,
    RawItem,
    majority_incomplete,
)
from news_insight.collect.http import fetch_checked, request_headers
from news_insight.collect.macros import expand_macros
from news_insight.net.mime import FEED_MIME
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.parsers.feed_probe import struct_to_datetime


class FeedCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        url = expand_macros(context.endpoint_url, now=context.now)
        response = fetch_checked(
            self._fetcher, url, allowed_mime=FEED_MIME, headers=request_headers(context)
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
        items = [raw for entry in window if (raw := _to_item(entry)) is not None]
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


def _to_item(entry: Any) -> RawItem | None:
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
        published_at=struct_to_datetime(
            entry.get("published_parsed") or entry.get("updated_parsed")
        ),
        author=str(entry.get("author") or "") or None,
        summary=str(entry.get("summary") or "") or None,
        body=body or None,
    )
