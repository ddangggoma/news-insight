from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.crawler import CrawlerCollector
from tests.helpers import mock_fetcher, serving

NOW = datetime(2026, 10, 3, tzinfo=UTC)
PAGE = """<html><body><ul class="news">
<li class="row"><a class="t" href="/news/1">과기정통부, 6G 로드맵 발표</a>
  <time class="d" datetime="2026-10-01T18:00:00">10.01</time><p class="s">요약 1</p></li>
<li class="row"><a class="t" href="https://www.example.go.kr/news/2">디지털 헬스 가이드라인</a>
  <span class="d">2026.10.02</span></li>
</ul></body></html>""".encode()
SELECTORS = {"item": "li.row", "title": "a.t", "link": "a.t", "date": ".d", "summary": "p.s"}


def collect(content: bytes, *, status: int = 200, **config: Any) -> Any:
    context = CollectContext(
        endpoint_url="https://www.example.go.kr/news/list",
        config={"selectors": SELECTORS, "timezone": "Asia/Seoul", **config},
        now=NOW,
    )
    return CrawlerCollector(serving(content, status=status, content_type="text/html")).collect(
        context
    )


def test_extracts_items_with_absolute_links_and_local_dates() -> None:
    first, second = collect(PAGE).items

    assert first.url == "https://www.example.go.kr/news/1"
    assert first.stable_id == "https://www.example.go.kr/news/1"
    assert (first.title, first.summary) == ("과기정통부, 6G 로드맵 발표", "요약 1")
    assert first.published_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert second.published_at == datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


def test_item_selector_without_matches_is_drift() -> None:
    with pytest.raises(CollectorError) as error:
        collect(PAGE, selectors={**SELECTORS, "item": "li.missing"})

    assert (error.value.code, error.value.retryable) == ("selector_drift", False)


def test_majority_incomplete_rows_signal_drift() -> None:
    page = (
        b'<ul><li class="row"><a class="t" href="/1">A</a></li>'
        + (b'<li class="row"><span class="t">no link</span></li>' * 2)
        + b"</ul>"
    )

    with pytest.raises(CollectorError) as error:
        collect(page)

    assert error.value.code == "selector_drift"


def test_missing_required_selectors_fail_before_fetching() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch")

    context = CollectContext(
        endpoint_url="https://www.example.go.kr/news/list",
        config={"selectors": {"item": "li"}},
        now=NOW,
    )

    with pytest.raises(CollectorError) as error:
        CrawlerCollector(mock_fetcher(explode)).collect(context)

    assert error.value.code == "config_error"
    assert "title, link" in str(error.value)


def test_not_modified() -> None:
    assert collect(b"", status=304).not_modified is True


def test_decodes_the_declared_charset() -> None:
    page = '<ul><li class="row"><a class="t" href="/k">전자정부 공지</a></li></ul>'.encode("euc-kr")
    context = CollectContext(
        endpoint_url="https://www.example.go.kr/news/list", config={"selectors": SELECTORS}, now=NOW
    )
    fetcher = serving(page, content_type="text/html; charset=EUC-KR")

    [only] = CrawlerCollector(fetcher).collect(context).items

    assert only.title == "전자정부 공지"
