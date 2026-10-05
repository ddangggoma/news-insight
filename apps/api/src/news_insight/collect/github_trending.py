"""Observe GitHub's unfiltered Trending lists; dates describe collection, not publication."""

import re
from urllib.parse import urljoin, urlsplit

from selectolax.parser import HTMLParser, Node

from news_insight.collect.contracts import CollectContext, CollectorError, CollectResult, RawItem
from news_insight.collect.http import fetch_checked, request_headers
from news_insight.content.normalize import clean_text
from news_insight.net.mime import HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher


def _count(node: Node | None) -> int | None:
    if node is None:
        return None
    text = node.text(strip=True).replace(",", "")
    match = re.match(r"^(\d+)(?:\s|$)", text)
    return int(match[1]) if match else None


def collect_trending(fetcher: SafeFetcher, context: CollectContext) -> CollectResult:
    kind = context.config.get("trending_kind", "repositories")
    period = context.config.get("trending_period", "daily")
    if kind not in {"repositories", "developers"} or period not in {"daily", "weekly", "monthly"}:
        raise CollectorError("config_error", "invalid Trending kind or period", retryable=False)
    response = fetch_checked(
        fetcher, context.endpoint_url, allowed_mime=HTML_MIME, headers=request_headers(context)
    )
    if response.status_code == 304:
        return CollectResult(
            items=[],
            status_code=304,
            elapsed_ms=response.elapsed_ms,
            not_modified=True,
            etag=context.etag,
            last_modified=context.last_modified,
        )
    tree = HTMLParser(response.content)
    rows = tree.css("article.Box-row")
    if not rows:
        raise CollectorError("selector_drift", "Trending rows missing", retryable=False)
    items: list[RawItem] = []
    for rank, row in enumerate(rows, 1):
        anchor = row.css_first("h2 a" if kind == "repositories" else "h1 a")
        href = anchor.attributes.get("href") if anchor is not None else None
        if not href:
            raise CollectorError("selector_drift", "Trending identity missing", retryable=False)
        url = urljoin(response.url, href)
        parts = urlsplit(url)
        identity = parts.path.strip("/")
        if parts.hostname != "github.com" or len(identity.split("/")) != (
            2 if kind == "repositories" else 1
        ):
            raise CollectorError("selector_drift", "unexpected Trending identity", retryable=False)
        metrics = {"rank": rank}
        description_node = row.css_first("p")
        description = clean_text(description_node.text()) if description_node is not None else None
        if kind == "repositories":
            for name, selector in (
                ("stars", 'a[href$="/stargazers"]'),
                ("forks", 'a[href$="/forks"]'),
                (f"trending_stars_{period}", "span.d-inline-block.float-sm-right"),
            ):
                count = _count(row.css_first(selector))
                if count is not None:
                    metrics[name] = count
            language = row.css_first('[itemprop="programmingLanguage"]')
            if language:
                description = f"{description or ''}\nLanguage: {language.text(strip=True)}".strip()
        items.append(
            RawItem(
                stable_id=f"github:{kind}:{identity.lower()}",
                url=f"https://github.com/{identity}",
                title=identity,
                summary=description,
                metrics=metrics,
            )
        )
    return CollectResult(
        items=items,
        status_code=200,
        elapsed_ms=response.elapsed_ms,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )
