"""Declarative HTML list crawler. V1 already requires terms review, robots check and selectors."""

from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from selectolax.parser import HTMLParser, Node

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
from news_insight.content.normalize import canonical_url, clean_text
from news_insight.net.safe_fetch import FetchResponse, SafeFetcher
from news_insight.sources.checks import EXPECTED_MIME
from news_insight.sources.enums import AccessMethod

HTML_MIME = EXPECTED_MIME[AccessMethod.CRAWLER]
REQUIRED_SELECTORS = ("item", "title", "link")


class CrawlerCollector:
    def __init__(self, fetcher: SafeFetcher) -> None:
        self._fetcher = fetcher

    def collect(self, context: CollectContext) -> CollectResult:
        selectors: dict[str, Any] = dict(context.config.get("selectors") or {})
        missing = [name for name in REQUIRED_SELECTORS if not selectors.get(name)]
        if missing:
            raise CollectorError(
                "config_error", f"missing selectors: {', '.join(missing)}", retryable=False
            )
        url = expand_macros(
            str(context.config.get("list_url") or context.endpoint_url), now=context.now
        )
        response = fetch_checked(
            self._fetcher, url, allowed_mime=HTML_MIME, headers=request_headers(context)
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
        nodes = HTMLParser(_decode(response)).css(str(selectors["item"]))[: context.item_limit]
        if not nodes:
            raise CollectorError(
                "selector_drift",
                f"item selector '{selectors['item']}' matched nothing",
                retryable=False,
            )
        tz = ZoneInfo(str(context.config.get("timezone", "UTC")))
        items = [
            raw
            for node in nodes
            if (raw := _to_item(node, selectors, base_url=response.url, tz=tz)) is not None
        ]
        incomplete = len(nodes) - len(items)
        if majority_incomplete(incomplete, len(nodes)):
            raise CollectorError(
                "selector_drift",
                f"{incomplete}/{len(nodes)} rows lack a title or link",
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


def _decode(response: FetchResponse) -> str:
    """Decode with the declared charset (e.g. EUC-KR portals); never guess from bytes."""
    content_type = response.headers.get("content-type", "")
    charset = "utf-8"
    if "charset=" in content_type:
        charset = (
            content_type.split("charset=", 1)[1].split(";", 1)[0].strip().strip('"') or charset
        )
    try:
        return response.content.decode(charset, errors="replace")
    except LookupError:
        return response.content.decode("utf-8", errors="replace")


def _text(node: Node | None) -> str | None:
    return clean_text(node.text(separator=" ")) if node is not None else None


def _to_item(
    node: Node, selectors: dict[str, Any], *, base_url: str, tz: ZoneInfo
) -> RawItem | None:
    title = _text(node.css_first(str(selectors["title"])))
    link_node = node.css_first(str(selectors["link"]))
    href = link_node.attributes.get("href") if link_node is not None else None
    if not (title and href):
        return None
    url = urljoin(base_url, href)
    published = None
    if selectors.get("date"):
        date_node = node.css_first(str(selectors["date"]))
        if date_node is not None:
            raw_date = date_node.attributes.get("datetime") or date_node.text()
            published = parse_datetime(raw_date, assume_tz=tz)
    summary = _text(node.css_first(str(selectors["summary"]))) if selectors.get("summary") else None
    return RawItem(
        stable_id=canonical_url(url), url=url, title=title, published_at=published, summary=summary
    )
