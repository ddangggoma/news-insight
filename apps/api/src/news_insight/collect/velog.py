"""Read public Velog post metadata from Next.js hydration JSON; never execute scripts."""

import json
import re
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from selectolax.parser import HTMLParser

from news_insight.collect.contracts import CollectContext, CollectorError, CollectResult, RawItem
from news_insight.collect.fields import parse_datetime
from news_insight.collect.http import fetch_checked, request_headers
from news_insight.content.normalize import clean_text
from news_insight.net.mime import HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher

PUSH = re.compile(r"^self\.__next_f\.push\((.*)\);?$", re.DOTALL)


def _posts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if "url_slug" in value and "user" in value:
            return [value]
        return [post for child in value.values() for post in _posts(child)]
    if isinstance(value, list):
        return [post for child in value for post in _posts(child)]
    return []


def collect_velog(fetcher: SafeFetcher, context: CollectContext) -> CollectResult:
    response = fetch_checked(
        fetcher, context.endpoint_url, allowed_mime=HTML_MIME, headers=request_headers(context)
    )
    if response.status_code == 304:
        return CollectResult([], 304, response.elapsed_ms, not_modified=True)
    posts: dict[str, dict[str, Any]] = {}
    for script in HTMLParser(response.content).css("script"):
        match = PUSH.fullmatch(script.text().strip())
        if match is None:
            continue
        try:
            chunk = json.loads(match.group(1))
        except ValueError:
            continue
        if not isinstance(chunk, list) or len(chunk) != 2 or not isinstance(chunk[1], str):
            continue
        for line in chunk[1].splitlines():
            try:
                value = json.loads(line.split(":", 1)[1])
            except (ValueError, IndexError):
                continue
            for post in _posts(value):
                if post.get("id"):
                    posts[str(post["id"])] = post
    if not posts:
        raise CollectorError(
            "selector_drift", "selector_drift: no Velog post data", retryable=False
        )
    cutoff = context.now - timedelta(days=float(context.config.get("max_age_days", 30)))
    items = []
    for stable_id, post in list(posts.items())[: context.item_limit]:
        if post.get("is_private") or post.get("is_temp"):
            continue
        user = post.get("user")
        author = user.get("username") if isinstance(user, dict) else None
        slug, title = post.get("url_slug"), clean_text(post.get("title"))
        published = parse_datetime(post.get("released_at"))
        if not (author and slug and title and published and cutoff <= published <= context.now):
            continue
        metrics = {
            name: value
            for name, field in (("likes", "likes"), ("comments", "comments_count"))
            if isinstance(value := post.get(field), int)
            and not isinstance(value, bool)
            and value >= 0
        }
        items.append(
            RawItem(
                stable_id=stable_id,
                url=f"https://velog.io/@{quote(str(author), safe='')}/{quote(str(slug), safe='')}",
                title=title,
                author=str(author),
                published_at=published,
                summary=clean_text(post.get("short_description")),
                metrics=metrics,
            )
        )
    return CollectResult(
        items,
        200,
        response.elapsed_ms,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )
