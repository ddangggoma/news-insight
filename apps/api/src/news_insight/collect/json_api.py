"""Generic JSON collector driven by a declarative mapping.

Mapping keys: `list_path`, `fields` (each a dotted path or a list of fallbacks),
`url_template` (`{a.b}` / `{a.b|last}`, used when no `fields.url` path yields a link),
`title_limit`, and `metrics` ({name: dotted path} of integer signals).
"""

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin

from news_insight.collect.contracts import (
    CollectContext,
    CollectorError,
    CollectResult,
    RawItem,
    majority_incomplete,
)
from news_insight.collect.fields import dotted_get, parse_datetime, text_or_none
from news_insight.collect.http import fetch_checked, request_headers
from news_insight.collect.macros import expand_macros
from news_insight.content.normalize import clean_text
from news_insight.net.mime import JSON_MIME
from news_insight.net.safe_fetch import SafeFetcher

DEFAULT_FIELDS: dict[str, Any] = {
    "id": "id",
    "url": "url",
    "title": "title",
    "summary": "summary",
    "published_at": "published_at",
    "author": "author",
}
PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_.\-]+)(\|last)?\}")


@dataclass(frozen=True)
class _Mapping:
    fields: dict[str, Any]
    url_template: str | None
    title_limit: int | None
    metrics: dict[str, Any]


class JsonApiCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        url = expand_macros(str(context.config.get("url") or context.endpoint_url), now=context.now)
        response = fetch_checked(
            self._fetcher, url, allowed_mime=JSON_MIME, headers=request_headers(context)
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
        mapping = _Mapping(
            fields={**DEFAULT_FIELDS, **dict(context.config.get("fields") or {})},
            url_template=str(context.config.get("url_template") or "") or None,
            title_limit=_int_or_none(context.config.get("title_limit")),
            metrics=dict(context.config.get("metrics") or {}),
        )
        window = records[: context.item_limit]
        items = [
            raw
            for record in window
            if (raw := _to_item(record, mapping, base_url=response.url)) is not None
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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _paths(spec: Any) -> list[str]:
    return [str(path) for path in spec] if isinstance(spec, list) else [str(spec)]


def first_value(record: Any, spec: Any) -> Any:
    for path in _paths(spec):
        value = dotted_get(record, path)
        if value not in (None, "", []):
            return value
    return None


def first_text(record: Any, spec: Any) -> str | None:
    for path in _paths(spec):
        value = text_or_none(dotted_get(record, path))
        if value:
            return value
    return None


def render_template(template: str, record: Any) -> str | None:
    missing = False

    def replace(match: re.Match[str]) -> str:
        nonlocal missing
        value = text_or_none(dotted_get(record, match.group(1)))
        if value is None:
            missing = True
            return ""
        if match.group(2):
            value = value.rstrip("/").rsplit("/", 1)[-1]
        return quote(value, safe="@.-_~")

    rendered = PLACEHOLDER.sub(replace, template)
    return None if missing else rendered


def extract_metrics(record: Any, mapping: dict[str, Any]) -> dict[str, int]:
    metrics: dict[str, int] = {}
    for name, path in mapping.items():
        value = dotted_get(record, str(path))
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            metrics[str(name)] = int(value)
        elif isinstance(value, str) and value.strip().isdigit():
            metrics[str(name)] = int(value.strip())
    return metrics


def _to_item(record: Any, mapping: _Mapping, *, base_url: str) -> RawItem | None:
    if not isinstance(record, dict):
        return None
    link = first_text(record, mapping.fields["url"])
    if link is None and mapping.url_template:
        link = render_template(mapping.url_template, record)
    title = first_text(record, mapping.fields["title"])
    if title and mapping.title_limit:
        title = clean_text(title, limit=mapping.title_limit)
    if not (link and title):
        return None
    url = urljoin(base_url, link)
    return RawItem(
        stable_id=first_text(record, mapping.fields["id"]) or url,
        url=url,
        title=title,
        published_at=parse_datetime(first_value(record, mapping.fields["published_at"])),
        author=first_text(record, mapping.fields["author"]),
        summary=first_text(record, mapping.fields["summary"]),
        metrics=extract_metrics(record, mapping.metrics),
    )
