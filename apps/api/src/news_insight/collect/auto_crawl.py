"""Auto crawler: find article links on list pages without per-site selectors.

A link counts as an article when it stays on the site, is not navigation (tag, category,
author, login, media files…), carries a headline-length anchor text and looks like an
article URL (an id or date in the path/query, or a long slug path). `config.link_pattern`
(regex) narrows it further for noisy sites.
"""

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

from news_insight.collect.contracts import CollectContext, CollectorError, CollectResult
from news_insight.collect.http import fetch_checked
from news_insight.collect.macros import expand_macros
from news_insight.collect.pages import Candidate, RobotsGate, complete, decode
from news_insight.content.normalize import clean_text
from news_insight.net.mime import HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher

NAVIGATION = re.compile(
    r"/(tags?|category|categories|section|sections|author|authors|writer|search|login|logout|"
    r"signup|register|join|subscribe|about|contact|privacy|terms|policy|faq|help|page|topics?|"
    r"rss|feed|newsletter|event|events|video|videos|photo|photos|gallery|shop|ads?)(/|$|\?)",
    re.IGNORECASE,
)
MEDIA = re.compile(r"\.(jpe?g|png|gif|webp|svg|pdf|zip|mp4|mp3|css|js|xml)$", re.IGNORECASE)
ARTICLE_HINT = re.compile(r"\d{4,}|/20\d\d/|/\d{1,2}/\d{1,2}/")
CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
MAX_LIST_PAGES = 3


def site_domain(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _headline(text: str) -> bool:
    return len(text) >= (8 if CJK.search(text) else 15)


def article_links(
    html: str, *, base_url: str, domain: str, pattern: str | None, drop_query: bool = False
) -> list[Candidate]:
    regex = re.compile(pattern) if pattern else None
    best: dict[str, str] = {}
    order: list[str] = []
    for anchor in HTMLParser(html).css("a[href]"):
        href = (anchor.attributes.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        parts = urlsplit(urljoin(base_url, href))
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not (
            host == domain or host.endswith("." + domain)
        ):
            continue
        url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, "" if drop_query else parts.query, "")
        )
        path_query = f"{parts.path}?{parts.query}"
        if parts.path in ("", "/") or MEDIA.search(parts.path) or NAVIGATION.search(path_query):
            continue
        text = clean_text(anchor.text(separator=" ")) or ""
        if regex is not None:
            if not regex.search(url):
                continue
        elif not (_headline(text) and (ARTICLE_HINT.search(path_query) or len(parts.path) > 40)):
            continue
        if url not in best:
            order.append(url)
            best[url] = text
        elif len(text) > len(best[url]):
            best[url] = text
    return [Candidate(url=url, title=best[url] or None) for url in order]


def collect_auto(fetcher: SafeFetcher, context: CollectContext) -> CollectResult:
    raw_urls = context.config.get("list_urls") or [
        context.config.get("list_url") or context.endpoint_url
    ]
    urls = [expand_macros(str(url), now=context.now) for url in list(raw_urls)[:MAX_LIST_PAGES]]
    pattern = context.config.get("link_pattern")
    domain = str(context.config.get("link_domain") or site_domain(urls[0]))
    candidates: list[Candidate] = []
    elapsed = 0
    for url in urls:
        response = fetch_checked(fetcher, url, allowed_mime=HTML_MIME, headers=context.headers)
        elapsed += response.elapsed_ms
        candidates.extend(
            article_links(
                decode(response),
                base_url=response.url,
                domain=domain,
                pattern=str(pattern) if pattern else None,
                drop_query=bool(context.config.get("drop_query")),
            )
        )
    if not candidates:
        raise CollectorError(
            "selector_drift", "no article links found on the list page(s)", retryable=False
        )
    items = complete(fetcher, candidates, context, robots=RobotsGate(fetcher))
    return CollectResult(items=items, status_code=200, elapsed_ms=elapsed)
