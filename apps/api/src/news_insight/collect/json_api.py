"""Generic JSON API collector driven by a declarative field mapping."""

import json
from typing import Any
from urllib.parse import urljoin

from news_insight.collect.contracts import (
    CollectContext,
    CollectorError,
    CollectResult,
    RawItem,
    majority_incomplete,
)
from news_insight.collect.fields import dotted_get, parse_datetime, text_or_none
from news_insight.collect.http import conditional_headers, fetch_checked
from news_insight.collect.macros import expand_macros
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import JSON_MIME

DEFAULT_FIELDS = {
    "id": "id",
    "url": "url",
    "title": "title",
    "summary": "summary",
    "published_at": "published_at",
    "author": "author",
}


class JsonApiCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        url = expand_macros(str(context.config.get("url") or context.endpoint_url), now=context.now)
        response = fetch_checked(
            self._fetcher, url, allowed_mime=JSON_MIME, headers=conditional_headers(context)
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
        try:
            payload = json.loads(response.content)
        except ValueError as exc:
            raise CollectorError(
                "parse_error", "response is not valid JSON", retryable=False
            ) from exc
        list_path = str(context.config.get("list_path", ""))
        records = dotted_get(payload, list_path)
        if not isinstance(records, list):
            raise CollectorError(
                "selector_drift", f"list_path '{list_path}' is not a list", retryable=False
            )
        fields = {**DEFAULT_FIELDS, **dict(context.config.get("fields") or {})}
        window = records[: context.item_limit]
        items = [
            raw
            for record in window
            if (raw := _to_item(record, fields, base_url=response.url)) is not None
        ]
        incomplete = len(window) - len(items)
        if majority_incomplete(incomplete, len(window)):
            raise CollectorError(
                "selector_drift",
                f"{incomplete}/{len(window)} records lack url or title",
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


def _to_item(record: Any, fields: dict[str, str], *, base_url: str) -> RawItem | None:
    if not isinstance(record, dict):
        return None
    link = text_or_none(dotted_get(record, fields["url"]))
    title = text_or_none(dotted_get(record, fields["title"]))
    if not (link and title):
        return None
    url = urljoin(base_url, link)
    return RawItem(
        stable_id=text_or_none(dotted_get(record, fields["id"])) or url,
        url=url,
        title=title,
        published_at=parse_datetime(dotted_get(record, fields["published_at"])),
        author=text_or_none(dotted_get(record, fields["author"])),
        summary=text_or_none(dotted_get(record, fields["summary"])),
    )
