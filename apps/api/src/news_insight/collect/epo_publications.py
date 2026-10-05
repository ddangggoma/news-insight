"""EPO's documented EPS REST API: a bounded latest-week bibliographic pilot.

The HTML index and XML bibliography are specified by the official REST guide.
This is a capped pilot, not a complete worldwide or weekly patent collection.
"""

import re
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

from selectolax.parser import HTMLParser

from news_insight.collect.contracts import CollectContext, CollectorError, CollectResult, RawItem
from news_insight.collect.http import fetch_checked
from news_insight.net.mime import FEED_MIME, HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher

ROOT = "https://data.epo.org/publication-server/rest/v1.2/publication-dates"
DATE_PATH = re.compile(r"^/publication-server/rest/v1\.2/publication-dates/(\d{8})/patents$")
PATENT_PATH = re.compile(r"^/publication-server/rest/v1\.2/patents/(EP\d+[A-Z][A-Z0-9]*)$")


def collect_publications(fetcher: SafeFetcher, context: CollectContext) -> CollectResult:
    if context.endpoint_url != ROOT:
        raise CollectorError(
            "config_error",
            "EPS adapter requires the documented date-list endpoint",
            retryable=False,
        )
    dates = fetch_checked(fetcher, ROOT, allowed_mime=HTML_MIME, headers=context.headers)
    available = {}
    for anchor in HTMLParser(dates.content).css("a[href]"):
        url = urljoin(ROOT, anchor.attributes.get("href") or "")
        parts = urlsplit(url)
        match = DATE_PATH.fullmatch(parts.path)
        if parts.hostname != "data.epo.org" or not match:
            continue
        try:
            published = datetime.strptime(match[1], "%Y%m%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        if published <= context.now:
            available[published] = url
    if not available:
        raise CollectorError("selector_drift", "EPS publication dates missing", retryable=False)
    published = max(available)
    listing = fetch_checked(
        fetcher, available[published], allowed_mime=HTML_MIME, headers=context.headers
    )
    items = {}
    for anchor in HTMLParser(listing.content).css("a[href]"):
        url = urljoin(listing.url, anchor.attributes.get("href") or "")
        parts = urlsplit(url)
        match = PATENT_PATH.fullmatch(parts.path)
        if parts.hostname != "data.epo.org" or not match:
            continue
        identifier = match[1]
        items[identifier] = RawItem(
            stable_id=f"epo:{identifier}",
            url=url,
            title=identifier,
            published_at=published,
            author="European Patent Office",
        )
    if not items:
        raise CollectorError(
            "selector_drift", "EPS weekly publication identifiers missing", retryable=False
        )
    completed = []
    elapsed = dates.elapsed_ms + listing.elapsed_ms
    limit = max(3, min(100, int(context.config.get("max_documents", 20))))
    for item in list(items.values())[:limit]:
        document = fetch_checked(
            fetcher, item.url + "/document.xml", allowed_mime=FEED_MIME, headers=context.headers
        )
        elapsed += document.elapsed_ms
        try:
            xml = ElementTree.fromstring(document.content)
        except ElementTree.ParseError as exc:
            raise CollectorError(
                "parse_error", "EPS bibliography is invalid XML", retryable=False
            ) from exc
        title = None
        titles = []
        language = ""
        for node in xml.findall(".//B540/*"):
            if node.tag == "B541":
                language = node.text or ""
            elif node.tag == "B542" and node.text:
                titles.append(node.text.strip())
                if language == "en":
                    title = node.text.strip()
        title = title or (titles[0] if titles else None)
        if not title:
            raise CollectorError("selector_drift", "EPS invention title missing", retryable=False)
        codes = []
        for node in xml.findall(".//classification-ipcr/text"):
            match = re.match(r"([A-H]\d\d[A-Z])\s+(\d+/\d+)", node.text or "")
            if match:
                codes.append(f"{match[1]} {match[2]}")
        summary = f"{item.title}; IPC: {', '.join(dict.fromkeys(codes))}" if codes else item.title
        completed.append(replace(item, title=title, summary=summary))
    return CollectResult(
        items=completed,
        status_code=200,
        elapsed_ms=elapsed,
    )
