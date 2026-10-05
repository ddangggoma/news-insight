from datetime import UTC, datetime

import httpx

from news_insight.collect.auto_crawl import article_links, collect_auto
from news_insight.collect.contracts import CollectContext
from news_insight.collect.page_meta import extract_meta
from news_insight.collect.sitemap import SitemapCollector
from news_insight.content.normalize import canonical_url, stable_key
from tests.helpers import mock_fetcher

NOW = datetime(2026, 10, 4, 3, tzinfo=UTC)
KST = __import__("zoneinfo").ZoneInfo("Asia/Seoul")

ARTICLE = """<html><head>
<meta property="og:title" content="삼성, 갤럭시 S30 공개">
<meta property="og:description" content="온디바이스 AI를 탑재한 새 플래그십">
<meta property="article:published_time" content="2026-10-04T09:30:00+09:00">
<title>삼성 - 예제신문</title></head><body><h1>다른 제목</h1></body></html>"""

LIST = """<html><body>
<nav><a href="/category/mobile">모바일 카테고리 전체 보기</a><a href="/login">로그인</a></nav>
<a href="/news/articleView.html?idxno=123456">삼성, 갤럭시 S30 공개하며 온디바이스 AI 강화</a>
<a href="https://www.example.co.kr/news/articleView.html?idxno=123457">
LG디스플레이 2세대 탠덤 OLED 양산</a>
<a href="/news/articleView.html?idxno=123456">삼성 갤럭시</a>
<a href="https://other.com/news/1234567">외부 사이트 기사 링크입니다 길게</a>
<a href="/photo/2026/10/04/123">사진 갤러리 오늘의 사진들 모음</a>
<a href="/news/articleView.html?idxno=999999">이미 수집한 기사 제목입니다</a>
</body></html>"""


def test_extract_meta_prefers_open_graph_and_parses_kst() -> None:
    meta = extract_meta(ARTICLE, assume_tz=KST)

    assert meta.title == "삼성, 갤럭시 S30 공개"
    assert meta.description == "온디바이스 AI를 탑재한 새 플래그십"
    assert meta.published_at == datetime(2026, 10, 4, 0, 30, tzinfo=UTC)


def test_extract_meta_falls_back_to_json_ld_and_time() -> None:
    ld = """<script type="application/ld+json">{"@graph":[{"@type":"WebPage"},
    {"@type":"NewsArticle","headline":"LD 제목","datePublished":"2026-10-03 18:00"}]}</script>"""
    meta = extract_meta(f"<html><head>{ld}</head></html>", assume_tz=KST)

    assert meta.title == "LD 제목"
    assert meta.published_at == datetime(2026, 10, 3, 9, 0, tzinfo=UTC)


def test_article_links_skip_navigation_media_and_other_sites() -> None:
    links = article_links(
        LIST, base_url="https://www.example.co.kr/", domain="example.co.kr", pattern=None
    )

    assert [link.url for link in links] == [
        "https://www.example.co.kr/news/articleView.html?idxno=123456",
        "https://www.example.co.kr/news/articleView.html?idxno=123457",
        "https://www.example.co.kr/news/articleView.html?idxno=999999",
    ]
    assert links[0].title == "삼성, 갤럭시 S30 공개하며 온디바이스 AI 강화"


def site(robots_txt: str | None = None) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            if robots_txt is None:
                return httpx.Response(404)
            return httpx.Response(
                200, headers={"content-type": "text/plain"}, content=robots_txt.encode()
            )
        if request.url.path == "/":
            return httpx.Response(
                200, headers={"content-type": "text/html; charset=utf-8"}, content=LIST.encode()
            )
        if request.url.path == "/sitemap.xml":
            return httpx.Response(
                200, headers={"content-type": "application/xml"}, content=SITEMAP_INDEX
            )
        if request.url.path == "/news-sitemap.xml":
            return httpx.Response(
                200, headers={"content-type": "application/xml"}, content=NEWS_SITEMAP
            )
        page = ARTICLE.replace(
            "S30 공개", f"S30 공개 {request.url.params.get('idxno', '')}".rstrip()
        )
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, content=page.encode()
        )

    return mock_fetcher(handler)


def context(url: str, **config: object) -> CollectContext:
    known = stable_key(
        canonical_url("https://www.example.co.kr/news/articleView.html?idxno=999999")
    )
    return CollectContext(
        endpoint_url=url,
        config={"timezone": "Asia/Seoul", **config},
        now=NOW,
        known_ids=frozenset({known}),
    )


def test_auto_crawl_completes_unseen_articles_from_their_pages() -> None:
    result = collect_auto(site(), context("https://www.example.co.kr/", mode="auto"))  # type: ignore[arg-type]

    assert [item.url for item in result.items] == [
        "https://www.example.co.kr/news/articleView.html?idxno=123456",
        "https://www.example.co.kr/news/articleView.html?idxno=123457",
    ]
    first = result.items[0]
    assert first.title == "삼성, 갤럭시 S30 공개 123456"
    assert first.summary == "온디바이스 AI를 탑재한 새 플래그십"
    assert first.published_at == datetime(2026, 10, 4, 0, 30, tzinfo=UTC)


def test_auto_crawl_keeps_anchor_titles_where_robots_forbids_article_pages() -> None:
    result = collect_auto(
        site("User-agent: *\nDisallow: /news/"),  # type: ignore[arg-type]
        context("https://www.example.co.kr/", mode="auto", enrich_limit=1),
    )

    assert [(item.title, item.published_at) for item in result.items] == [
        ("삼성, 갤럭시 S30 공개하며 온디바이스 AI 강화", None)
    ]


SITEMAP_INDEX = b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.example.co.kr/sitemap-pages.xml</loc></sitemap>
<sitemap><loc>https://www.example.co.kr/news-sitemap.xml</loc></sitemap>
</sitemapindex>"""
NEWS_SITEMAP = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>https://www.example.co.kr/news/articleView.html?idxno=1</loc>
<news:news><news:title>older</news:title><news:publication_date>2026-10-03T08:00:00+09:00</news:publication_date></news:news></url>
<url><loc>https://www.example.co.kr/news/articleView.html?idxno=2</loc>
<news:news><news:title>newer</news:title><news:publication_date>2026-10-04T08:00:00+09:00</news:publication_date></news:news></url>
<url><loc>https://www.example.co.kr/news/articleView.html?idxno=999999</loc>
<news:news><news:title>known</news:title><news:publication_date>2026-10-04T09:00:00+09:00</news:publication_date></news:news></url>
</urlset>"""


def test_sitemap_index_prefers_news_sitemap_and_orders_by_date() -> None:
    result = SitemapCollector(site()).collect(context("https://www.example.co.kr/sitemap.xml"))  # type: ignore[arg-type]

    assert [item.title for item in result.items] == ["newer", "older"]
    assert result.items[0].published_at == datetime(2026, 10, 3, 23, 0, tzinfo=UTC)
    assert result.items[0].summary == "온디바이스 AI를 탑재한 새 플래그십"


def test_shared_og_title_falls_back_to_anchor_and_undated_pages_are_dropped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/":
            return httpx.Response(200, headers={"content-type": "text/html"}, content=LIST.encode())
        idxno = request.url.params.get("idxno")
        dated = '<meta property="article:published_time" content="2026-10-04T09:30:00+09:00">'
        head = f'<meta property="og:title" content="SITE">{dated if idxno == "123456" else ""}'
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=f"<html><head>{head}</head></html>".encode(),
        )

    result = collect_auto(mock_fetcher(handler), context("https://www.example.co.kr/", mode="auto"))
    fallback = collect_auto(
        mock_fetcher(handler),
        context("https://www.example.co.kr/", mode="auto", date_fallback="now"),
    )

    assert [item.title for item in result.items] == ["삼성, 갤럭시 S30 공개하며 온디바이스 AI 강화"]
    assert [item.title for item in fallback.items] == [
        "삼성, 갤럭시 S30 공개하며 온디바이스 AI 강화",
        "LG디스플레이 2세대 탠덤 OLED 양산",
    ]
    assert fallback.items[1].published_at == NOW


def test_shared_site_suffix_is_stripped() -> None:
    from news_insight.collect.contracts import RawItem
    from news_insight.collect.pages import strip_site_suffix

    items = [
        RawItem(stable_id="a", url="https://x/a", title="아이폰 판매량 증가 : 클리앙"),
        RawItem(stable_id="b", url="https://x/b", title="신한은행 개인정보 유출 : 클리앙"),
        RawItem(stable_id="c", url="https://x/c", title="Pixel 11 review - hands on"),
    ]

    assert [item.title for item in strip_site_suffix(items)] == [
        "아이폰 판매량 증가",
        "신한은행 개인정보 유출",
        "Pixel 11 review - hands on",
    ]


def test_sitemap_skips_archive_pages_by_listing_date_and_by_page_date() -> None:
    # 2026-10-05: sitemaps walked back through whole sites, 15 old pages a run
    sitemap = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.example.co.kr/new</loc><lastmod>2026-10-03</lastmod></url>
<url><loc>https://www.example.co.kr/old-listed</loc><lastmod>2013-05-01</lastmod></url>
<url><loc>https://www.example.co.kr/old-undated</loc></url>
</urlset>"""
    old_page = ARTICLE.replace("2026-10-04T09:30:00+09:00", "2014-01-01T09:00:00+09:00")
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        fetched.append(url)
        if url.endswith("robots.txt"):
            return httpx.Response(404)
        if url.endswith("sitemap.xml"):
            return httpx.Response(200, content=sitemap, headers={"content-type": "application/xml"})
        body = old_page if "old-undated" in url else ARTICLE
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    collector = SitemapCollector(mock_fetcher(handler))
    result = collector.collect(context("https://www.example.co.kr/sitemap.xml"))

    assert [item.url for item in result.items] == ["https://www.example.co.kr/new"]
    assert not any("old-listed" in url for url in fetched)  # skipped before any fetch
    # a source can ask for a longer window
    longer = collector.collect(context("https://www.example.co.kr/sitemap.xml", max_age_days=10000))
    assert len(longer.items) == 3


def test_openalex_requests_carry_the_contact_address(monkeypatch: object) -> None:
    from news_insight.collect import context as ctx
    from news_insight.config import get_settings

    settings = get_settings()
    original = settings.openalex_mailto
    try:
        object.__setattr__(settings, "openalex_mailto", "someone@example.com")
        url = "https://api.openalex.org/works?filter=from_publication_date:{today-30d}&per-page=50"
        assert ctx.polite_url(url) == url + "&mailto=someone@example.com"
        assert ctx.polite_url(url + "&mailto=x@y.z") == url + "&mailto=x@y.z"
        assert ctx.polite_url("https://example.com/feed") == "https://example.com/feed"
    finally:
        object.__setattr__(settings, "openalex_mailto", original)
