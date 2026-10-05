from datetime import UTC, datetime

import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.crawler import CrawlerCollector
from tests.helpers import serving

NOW = datetime(2026, 10, 5, tzinfo=UTC)
PAGE = b"""<html><body><h1>Trending</h1><article class="Box-row">
<h2><a href="/owner/project">owner / project</a></h2><p>Project description</p>
<span itemprop="programmingLanguage">Python</span>
<a href="/owner/project/stargazers">1,234</a><a href="/owner/project/forks">56</a>
<span class="d-inline-block float-sm-right">123 stars today</span></article></body></html>"""


def collect(page: bytes, *, kind: str = "repositories"):
    return CrawlerCollector(serving(page, content_type="text/html")).collect(
        CollectContext(
            endpoint_url="https://github.com/trending?since=daily",
            config={"mode": "github_trending", "trending_kind": kind, "trending_period": "daily"},
            now=NOW,
        )
    )


def test_repository_observation_preserves_rank_and_metrics_without_inventing_publication():
    [item] = collect(PAGE).items
    assert item.url == "https://github.com/owner/project"
    assert item.title == "owner/project"
    assert item.published_at is None
    assert item.metrics == {"rank": 1, "stars": 1234, "forks": 56, "trending_stars_daily": 123}
    assert "Python" in item.summary


def test_collects_every_displayed_row_without_a_theme_filter():
    page = PAGE.replace(b"owner/project", b"owner/quantum") + PAGE.replace(
        b"owner/project", b"owner/battery"
    )
    assert [item.title for item in collect(page).items] == ["owner/quantum", "owner/battery"]


def test_markup_drift_is_not_reported_as_empty_success():
    with pytest.raises(CollectorError) as error:
        collect(b"<html><h1>Something changed</h1></html>")
    assert error.value.code == "selector_drift"


def test_developer_observation_uses_public_profile_and_rank():
    page = b'<article class="Box-row"><h1><a href="/example">Example</a></h1></article>'
    [item] = collect(page, kind="developers").items
    assert item.url == "https://github.com/example"
    assert item.title == "example"
    assert item.metrics == {"rank": 1}
    assert item.published_at is None


def test_declarative_date_format_and_session_free_identity():
    page = (
        b'<table><tr><td class="title">'
        b'<a href="/view;jsessionid=ABC?id=7&amp;page=2">Research news</a>'
        b'</td><td class="date">Sep 29, 2026</td></tr></table>'
    )
    context = CollectContext(
        endpoint_url="https://example.com/list",
        now=NOW,
        config={
            "selectors": {"item": "tr", "title": "td.title a", "link": "a", "date": "td.date"},
            "date_format": "%b %d, %Y",
            "normalize_query": ["id"],
            "strip_session": True,
        },
    )
    [item] = CrawlerCollector(serving(page, content_type="text/html")).collect(context).items
    assert item.url == "https://example.com/view?id=7"
    assert item.published_at == datetime(2026, 9, 29, tzinfo=UTC)
