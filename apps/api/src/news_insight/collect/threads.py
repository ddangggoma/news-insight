"""Read public Threads posts from the JSON a logged-out page embeds; never execute scripts.

A logged-out keyword search (`/search?q=...`) or profile (`/@name`) page carries its first
posts, with like, reply, repost and quote counts, in a `<script type="application/json">`
block. We send our own user agent (no browser disguise), no cookies and no login: the user
chose this small-scale logged-out crawl on 2026-11-18 while the official Threads API
application is reviewed (docs/runbooks/threads-api.md).

Threads answers a navigation request with the data only when it carries the browser's
`Sec-Fetch-*` navigation headers, which describe the request (a top-level page load) and
not the client. A page without the data is a login wall, a soft block or a layout change:
it backs off every Threads source for an hour (`rate_limited`), and the retry ladder pauses
the source when it persists.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlsplit

from selectolax.parser import HTMLParser

from news_insight.collect.contracts import CollectContext, CollectorError, CollectResult, RawItem
from news_insight.collect.http import fetch_checked, request_headers
from news_insight.content.normalize import clean_text
from news_insight.net.mime import HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher

NAVIGATION_HEADERS = {
    "Accept": "text/html",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Site": "none",
}
# the result lists a search page (searchResults) or a profile page (mediaData) embeds
CONTAINERS = ('"searchResults"', '"mediaData"')
THREADS_HOSTS = frozenset({"threads.com", "www.threads.com", "threads.net", "www.threads.net"})
BACKOFF_SECONDS = 3600
SUMMARY_LIMIT = 500
TITLE_LIMIT = 200
URL = re.compile(r"https?://[^\s<>\"']+")
METRICS = (
    ("replies", "direct_reply_count"),
    ("reposts", "repost_count"),
    ("quotes", "quote_count"),
    ("reshares", "reshare_count"),
)


def _posts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if "code" in value and "taken_at" in value and "user" in value:
            return [value]
        return [post for child in value.values() for post in _posts(child)]
    if isinstance(value, list):
        return [post for child in value for post in _posts(child)]
    return []


def _count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _metrics(post: dict[str, Any]) -> dict[str, int]:
    metrics: dict[str, int] = {}
    if not post.get("like_and_view_counts_disabled"):
        likes = _count(post.get("like_count"))
        if likes is not None:
            metrics["likes"] = likes
    info = post.get("text_post_app_info")
    if isinstance(info, dict):
        for name, field in METRICS:
            value = _count(info.get(field))
            if value is not None:
                metrics[name] = value
    return metrics


def _shared_link(post: dict[str, Any], text: str) -> str | None:
    """The external page a post shares: its link preview, else the first URL in its text."""
    info = post.get("text_post_app_info")
    preview = info.get("link_preview_attachment") if isinstance(info, dict) else None
    candidates = [preview.get("url")] if isinstance(preview, dict) else []
    candidates += URL.findall(text)
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        url = candidate.rstrip(".,;:!?)")
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            continue
        if host and host not in THREADS_HOSTS and not host.endswith(".threads.com"):
            return url
    return None


def _item(post: dict[str, Any], *, cutoff: datetime, now: datetime) -> RawItem | None:
    info = post.get("text_post_app_info")
    if isinstance(info, dict) and info.get("reply_to_author"):
        return None  # a reply or a thread's continuation, not a post of its own
    user = post.get("user")
    author = user.get("username") if isinstance(user, dict) else None
    code = post.get("code")
    taken_at = _count(post.get("taken_at"))
    caption = post.get("caption")
    text = caption.get("text") if isinstance(caption, dict) else None
    if not (isinstance(author, str) and author and isinstance(code, str) and code and taken_at):
        return None
    if not isinstance(text, str) or not text.strip():
        return None  # an image or video without words
    published = datetime.fromtimestamp(taken_at, UTC)
    if not cutoff <= published <= now + timedelta(minutes=5):
        return None
    first_line = next(line for line in text.splitlines() if line.strip())
    title = clean_text(first_line, limit=TITLE_LIMIT)
    if not title:
        return None
    return RawItem(
        stable_id=code,
        url=f"https://www.threads.com/@{quote(author, safe='._')}/post/{quote(code, safe='-_')}",
        title=title,
        author=author,
        published_at=published,
        summary=clean_text(text, limit=SUMMARY_LIMIT),
        metrics=_metrics(post),
        link=_shared_link(post, text),
    )


def collect_threads(fetcher: SafeFetcher, context: CollectContext) -> CollectResult:
    headers = {**NAVIGATION_HEADERS, **request_headers(context)}
    response = fetch_checked(fetcher, context.endpoint_url, allowed_mime=HTML_MIME, headers=headers)
    if response.status_code == 304:
        return CollectResult([], 304, response.elapsed_ms, not_modified=True)
    found = False
    posts: dict[str, dict[str, Any]] = {}
    for script in HTMLParser(response.content).css('script[type="application/json"]'):
        text = script.text()
        if not any(container in text for container in CONTAINERS):
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        found = True
        for post in _posts(data):
            code = post.get("code")
            if isinstance(code, str) and code:
                posts.setdefault(code, post)
    if not found:
        raise CollectorError(
            "rate_limited",
            f"no Threads post data in {response.url} (login wall, block or layout change)",
            retryable=True,
            status_code=response.status_code,
            retry_after=BACKOFF_SECONDS,
        )
    cutoff = context.now - timedelta(days=float(context.config.get("max_age_days", 7)))
    items = [
        item
        for post in list(posts.values())[: context.item_limit]
        if (item := _item(post, cutoff=cutoff, now=context.now)) is not None
    ]
    return CollectResult(items, 200, response.elapsed_ms)
