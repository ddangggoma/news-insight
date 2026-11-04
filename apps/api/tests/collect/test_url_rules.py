"""URL include/exclude rules of the page collectors (2026-11-04 audit): board rule pages, CMS
demo pages, a language copy of every post and forum threads are not articles."""

import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from news_insight.collect.auto_crawl import article_links, collect_auto
from news_insight.collect.contracts import CollectContext
from news_insight.collect.crawler import CrawlerCollector
from news_insight.collect.pages import exclusion
from news_insight.collect.sitemap import SitemapCollector
from news_insight.sources.catalog import load_catalog
from tests.helpers import mock_fetcher, serving

NOW = datetime(2026, 11, 4, 3, tzinfo=UTC)
ARTICLE = """<html><head><meta property="og:title" content="Page">
<meta property="article:published_time" content="2026-11-03T09:00:00Z"></head></html>"""


def test_exclusion_takes_one_regex_or_a_list_and_each_may_set_flags() -> None:
    assert exclusion({}) is None
    assert exclusion({"exclude_pattern": []}) is None
    single = exclusion({"exclude_pattern": "/rule/"})
    assert single is not None and single.search("https://x.net/board/rule/1")
    assert not single.search("https://x.net/board/news/1")
    several = exclusion({"exclude_pattern": ["/rule/", "(?i)/EXAMPLE-"]})
    assert several is not None
    assert several.search("https://x.net/a/example-page") and several.search("https://x.net/rule/")
    assert not several.search("https://x.net/a/news")


def test_auto_crawl_drops_excluded_links_before_fetching_their_pages() -> None:
    html = """<body>
<a href="/service/board/news/19000001">삼성전자 새 폴더블 스마트폰 공개 소식입니다</a>
<a href="/service/board/rule/10707403">게시판 이용 규칙을 안내해 드립니다 꼭 읽어주세요</a>
<a href="/service/board/annonce/18708788">운영진 공지사항을 안내해 드립니다 꼭 읽어주세요</a>
</body>"""
    links = article_links(
        html,
        base_url="https://www.clien.net/service/board/news",
        domain="clien.net",
        pattern=None,
        exclude=exclusion({"exclude_pattern": "/service/board/(rule|annonce)/"}),
    )

    assert [link.url for link in links] == ["https://www.clien.net/service/board/news/19000001"]
    unfiltered = article_links(
        html, base_url="https://www.clien.net/", domain="clien.net", pattern=None
    )
    assert len(unfiltered) == 3


def test_auto_crawl_collect_never_fetches_an_excluded_page() -> None:
    fetched: list[str] = []
    listing = """<a href="/news/articleView.html?idxno=123456">삼성, 갤럭시 S30 공개하며 AI 강화</a>
<a href="/rule/10707403">게시판 이용 규칙을 안내해 드립니다 꼭 읽어주세요</a>"""

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        body = listing if request.url.path == "/" else ARTICLE
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    context = CollectContext(
        endpoint_url="https://www.example.co.kr/",
        config={"mode": "auto", "exclude_pattern": "/rule/"},
        now=NOW,
    )
    result = collect_auto(mock_fetcher(handler), context)

    assert [item.url for item in result.items] == [
        "https://www.example.co.kr/news/articleView.html?idxno=123456"
    ]
    assert "/rule/10707403" not in fetched


SITEMAP = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://mistral.ai/news/mistral-large-4</loc><lastmod>2026-11-03</lastmod></url>
<url><loc>https://mistral.ai/fr/news/mistral-large-4</loc><lastmod>2026-11-03</lastmod></url>
<url><loc>https://mistral.ai/it/news/mistral-large-4</loc><lastmod>2026-11-03</lastmod></url>
<url><loc>https://mistral.ai/news</loc><lastmod>2026-11-03</lastmod></url>
<url><loc>https://mistral.ai/customers/ardian</loc><lastmod>2026-11-03</lastmod></url>
</urlset>"""


def sitemap_collect(**config: Any) -> tuple[list[str], list[str]]:
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/sitemap.xml":
            return httpx.Response(200, content=SITEMAP, headers={"content-type": "application/xml"})
        return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})

    context = CollectContext(endpoint_url="https://mistral.ai/sitemap.xml", config=config, now=NOW)
    result = SitemapCollector(mock_fetcher(handler)).collect(context)
    return [item.url for item in result.items], fetched


def test_sitemap_link_pattern_keeps_one_language() -> None:
    urls, fetched = sitemap_collect(link_pattern=r"^https://mistral\.ai/news/[^/?#]+/?$")

    assert urls == ["https://mistral.ai/news/mistral-large-4"]
    assert not any("/fr/" in url or "/it/" in url for url in fetched)


def test_sitemap_exclude_pattern_drops_pages_before_they_are_fetched() -> None:
    urls, fetched = sitemap_collect(exclude_pattern=["/(fr|it)/", "/customers/"])

    assert sorted(urls) == ["https://mistral.ai/news", "https://mistral.ai/news/mistral-large-4"]
    assert not any("/customers/" in url for url in fetched)


def test_sitemap_with_everything_excluded_is_drift_not_an_empty_success() -> None:
    from news_insight.collect.contracts import CollectorError

    with pytest.raises(CollectorError) as error:
        sitemap_collect(exclude_pattern=".")

    assert error.value.code == "selector_drift"


def test_declared_crawler_honours_exclude_pattern() -> None:
    page = b"""<ul>
<li class="r"><a href="/news/1">6G roadmap announced by the ministry</a></li>
<li class="r"><a href="/notice/2">Board rules and notices for members</a></li></ul>"""
    context = CollectContext(
        endpoint_url="https://www.example.go.kr/list",
        config={
            "selectors": {"item": "li.r", "title": "a", "link": "a"},
            "exclude_pattern": "/notice/",
        },
        now=NOW,
    )

    result = CrawlerCollector(serving(page, content_type="text/html")).collect(context)

    assert [item.url for item in result.items] == ["https://www.example.go.kr/news/1"]


CATALOG = {entry.key: entry.config for entry in load_catalog().sources}


def junk(key: str, url: str) -> bool:
    from news_insight.content.hide import is_junk

    return is_junk(url, CATALOG[key])


def test_every_catalog_pattern_compiles() -> None:
    for config in CATALOG.values():
        assert exclusion(config) is not None or "exclude_pattern" not in config
        if config.get("link_pattern"):
            re.compile(str(config["link_pattern"]))  # a typo would fail on the first run


@pytest.mark.parametrize("key", ["clien-news", "clien-cm-ittalk"])
def test_clien_rule_and_notice_pages_are_not_articles(key: str) -> None:
    assert junk(key, "https://www.clien.net/service/board/rule/10707403")
    assert junk(key, "https://www.clien.net/service/board/annonce/18708788")
    assert not junk(key, "https://www.clien.net/service/board/news/19012345")
    assert not junk(key, "https://www.clien.net/service/board/use/19012345")


def test_cea_template_and_demo_pages_are_not_articles() -> None:
    base = "https://www.cea.fr:443/paris-saclay/jf/"
    assert junk("cea-leti-web", base + "liste-de-pages-avancees/exemple-de-page")
    assert junk(
        "cea-leti-web", base + "liste-de-pages-multimedias/exemple-avec-une-animation-flash"
    )
    assert not junk(
        "cea-leti-web",
        "https://www.cea.fr:443/cea-tech/leti/english/Pages/What's-On/News/LIPIDOTS.aspx",
    )


def test_mistral_keeps_the_english_post_only() -> None:
    assert not junk("mistral-news-web", "https://mistral.ai/news/mistral-large-4")
    assert not junk("mistral-news-web", "https://mistral.ai/news/mistral-large-4/")
    assert junk("mistral-news-web", "https://mistral.ai/fr/news/mistral-large-4")
    assert junk("mistral-news-web", "https://mistral.ai/it/news/mistral-large-4")
    assert junk("mistral-news-web", "https://mistral.ai/news/")
    assert junk("mistral-news-web", "https://mistral.ai/customers/ardian")


def test_continental_keeps_press_releases_not_investor_calendars() -> None:
    press = "https://www.continental.com/en/press/press-releases/2026-10-26-new-tire/"
    calendar = "https://www.continental.com/en/investors/events/financial-calendar/2026-q3/"
    assert not junk("continental-press-web", press)
    assert junk("continental-press-web", calendar)
    assert junk("continental-press-web", "https://www.continental.com/en/career/working/")


def test_openwrt_collects_the_announcements_category_only() -> None:
    entry = next(e for e in load_catalog().sources if e.key == "openwrt-news-web")

    assert entry.access_method.value == "feed"
    assert entry.endpoint_url == "https://forum.openwrt.org/c/announcements/14.rss"
