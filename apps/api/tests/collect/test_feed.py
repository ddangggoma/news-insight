from datetime import UTC, datetime

import httpx
import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.feed import FeedCollector
from tests.helpers import serving
from tests.parsers.test_feed_probe import RECENT, item, rss

NOW = datetime(2026, 10, 3, tzinfo=UTC)
RICH = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<title>t</title><link>https://www.example.com</link><description>d</description>
<item><guid>g-1</guid><link>https://www.example.com/a</link><title>Galaxy S30</title>
<description>&lt;p&gt;Short&lt;/p&gt;</description>
<content:encoded><![CDATA[<p>Full body</p>]]></content:encoded>
<pubDate>Thu, 01 Oct 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""


def context(**overrides: object) -> CollectContext:
    values: dict[str, object] = {
        "endpoint_url": "https://www.example.com/feed.xml",
        "config": {},
        "now": NOW,
        **overrides,
    }
    return CollectContext(**values)  # type: ignore[arg-type]


def test_parses_entries_into_raw_items() -> None:
    fetcher = serving(RICH, headers={"etag": '"v1"', "last-modified": "Thu, 01 Oct 2026"})

    result = FeedCollector(fetcher).collect(context())

    [first] = result.items
    assert (first.stable_id, first.url, first.title) == (
        "g-1",
        "https://www.example.com/a",
        "Galaxy S30",
    )
    assert first.summary is not None and "Short" in first.summary
    assert first.body == "<p>Full body</p>"
    assert first.published_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    assert (result.etag, result.last_modified) == ('"v1"', "Thu, 01 Oct 2026")


def test_sends_conditional_headers() -> None:
    seen: list[httpx.Request] = []

    FeedCollector(serving(rss(item(1)), seen=seen)).collect(
        context(etag='"v1"', last_modified="Thu, 01 Oct 2026 09:00:00 GMT")
    )

    assert seen[0].headers["if-none-match"] == '"v1"'
    assert seen[0].headers["if-modified-since"] == "Thu, 01 Oct 2026 09:00:00 GMT"


def test_not_modified_keeps_validators() -> None:
    result = FeedCollector(serving(b"", status=304)).collect(context(etag='"v1"'))

    assert (result.not_modified, result.items, result.status_code, result.etag) == (
        True,
        [],
        304,
        '"v1"',
    )


def test_empty_feed_is_not_drift() -> None:
    result = FeedCollector(serving(rss())).collect(context())

    assert (result.items, result.incomplete) == ([], 0)


def test_majority_incomplete_entries_signal_drift() -> None:
    untitled = [
        {"guid": f"g-{n}", "link": f"https://www.example.com/{n}", "title": "", "date": RECENT}
        for n in (2, 3)
    ]

    with pytest.raises(CollectorError) as error:
        FeedCollector(serving(rss(item(1), *untitled))).collect(context())

    assert (error.value.code, error.value.retryable) == ("selector_drift", False)


def test_garbage_is_a_parse_error() -> None:
    with pytest.raises(CollectorError) as error:
        FeedCollector(serving(b"definitely not a feed")).collect(context())

    assert error.value.code == "parse_error"


def test_endpoint_macros_are_expanded() -> None:
    seen: list[httpx.Request] = []

    FeedCollector(serving(rss(item(1)), seen=seen)).collect(
        context(endpoint_url="https://www.example.com/feed?since={today-1d}")
    )

    assert seen[0].url.params["since"] == "2026-10-02"


def test_rate_limit_is_retryable() -> None:
    with pytest.raises(CollectorError) as error:
        FeedCollector(serving(b"", status=429)).collect(context())

    assert (error.value.code, error.value.retryable) == ("rate_limited", True)


ZONELESS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title><link>https://www.example.com</link>
<description>d</description>
<item><guid>g-1</guid><link>https://www.example.com/a</link><title>a</title>
<pubDate>2026-10-02 08:09:31</pubDate></item>
<item><guid>g-2</guid><link>https://www.example.com/b</link><title>b</title>
<pubDate>Fri, 02 Oct 2026 08:00:00 +0900</pubDate></item>
</channel></rss>"""


def test_zoneless_dates_are_the_source_local_time() -> None:
    result = FeedCollector(serving(ZONELESS)).collect(context(config={"timezone": "Asia/Seoul"}))

    zoneless, zoned = result.items
    assert zoneless.published_at == datetime(2026, 10, 1, 23, 9, 31, tzinfo=UTC)
    assert zoned.published_at == datetime(2026, 10, 1, 23, 0, tzinfo=UTC)


def test_zoneless_dates_stay_utc_without_a_zone() -> None:
    zoneless, _ = FeedCollector(serving(ZONELESS)).collect(context()).items

    assert zoneless.published_at == datetime(2026, 10, 2, 8, 9, 31, tzinfo=UTC)


def test_a_feed_labelled_html_is_read_by_its_body() -> None:
    # krebsonsecurity.com/feed/ serves valid RSS as text/html (2026-10-29)
    result = FeedCollector(serving(RICH, content_type="text/html")).collect(context())

    assert [raw.title for raw in result.items] == ["Galaxy S30"]


@pytest.mark.parametrize(
    "page",
    [
        b"<!doctype html><html><body>Please accept cookies</body></html>",
        b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body/></html>',
    ],
)
def test_an_html_page_is_still_a_wrong_content_type(page: bytes) -> None:
    with pytest.raises(CollectorError) as error:
        FeedCollector(serving(page, content_type="text/html")).collect(context())

    assert (error.value.code, error.value.retryable) == ("blocked_mime", False)
