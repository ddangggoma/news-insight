from datetime import UTC, datetime

from news_insight.collect.auto_crawl import article_links
from news_insight.collect.contracts import CollectContext
from news_insight.collect.pages import Candidate, complete
from tests.helpers import serving


def test_article_selector_excludes_pinned_and_navigation_rows():
    html = (
        '<a href="/en/news-and-ideas/old">Old news</a>'
        '<section class="latest"><a href="/en/news-and-ideas/new">New news</a></section>'
    )
    links = article_links(
        html,
        base_url="https://example.com",
        domain="example.com",
        pattern="/en/news-and-ideas/",
        selector="section.latest a[href]",
    )
    assert [c.url for c in links] == ["https://example.com/en/news-and-ideas/new"]


def test_official_printed_publication_date_completes_article():
    page = (
        b"<h1>Research achievement</h1>"
        b'<p class="date"><span>Author</span><span>29 September 2026</span></p>'
    )
    context = CollectContext(
        endpoint_url="https://example.com/news",
        now=datetime(2026, 10, 5, tzinfo=UTC),
        config={"article_date_selector": "p.date span", "article_date_format": "%d %B %Y"},
    )

    class Allowed:
        def allows(self, url):
            return True

    [item] = complete(
        serving(page, content_type="text/html"),
        [Candidate("https://example.com/news/1")],
        context,
        robots=Allowed(),
    )
    assert item.published_at == datetime(2026, 9, 29, tzinfo=UTC)


def test_declarative_research_listing_skips_archive_and_future_dates():
    from news_insight.collect.crawler import CrawlerCollector

    page = b"".join(
        (
            f'<article><a href="/{date}">Research news</a><time datetime="{date}"></time></article>'
        ).encode()
        for date in ("2026-09-29", "2020-01-01", "2026-10-10")
    )
    context = CollectContext(
        endpoint_url="https://example.com/list",
        now=datetime(2026, 10, 5, tzinfo=UTC),
        config={
            "max_age_days": 30,
            "selectors": {"item": "article", "title": "a", "link": "a", "date": "time"},
        },
    )
    result = CrawlerCollector(serving(page, content_type="text/html")).collect(context)
    assert len(result.items) == 1
    assert result.incomplete == 0


def test_crossref_full_publication_date_parts_and_unknown_precision():
    from news_insight.collect.fields import parse_datetime

    assert parse_datetime([2026, 9, 29]) == datetime(2026, 9, 29, tzinfo=UTC)
    assert parse_datetime([2026, 9]) is None
    assert parse_datetime([2026, 2, 31]) is None
