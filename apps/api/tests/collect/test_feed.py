from datetime import UTC, datetime

import httpx
import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.feed import FeedCollector
from news_insight.content.normalize import stable_key
from news_insight.net.safe_fetch import SafeFetcher
from tests.helpers import mock_fetcher, serving
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


LABELLED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title><link>https://www.example.com</link><description>d</description>
<item><guid>s-1</guid><link>https://www.example.com/a</link><title>a</title>
<pubDate>Tue, 03 Nov 2026 08:00:00 +0000</pubDate></item>
</channel></rss>"""


def test_local_clock_reads_a_wall_clock_labelled_utc_in_the_source_zone() -> None:
    # Samsung Newsroom: "08:00:00 +0000" for a page that says 2026-11-03T08:00:00+09:00
    config = {"timezone": "Asia/Seoul", "local_clock": True}

    [labelled] = FeedCollector(serving(LABELLED)).collect(context(config=config)).items
    [honest] = FeedCollector(serving(LABELLED)).collect(context()).items

    assert labelled.published_at == datetime(2026, 11, 2, 23, 0, tzinfo=UTC)
    assert honest.published_at == datetime(2026, 11, 3, 8, 0, tzinfo=UTC)


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


def test_a_source_may_raise_the_size_limit() -> None:
    big = RICH.replace(b"<title>t</title>", b"<title>t</title>" + b"<!--" + b"x" * 6000 + b"-->")
    limited = serving(big)
    limited._max_bytes = 4096  # the default limit, scaled down

    with pytest.raises(CollectorError) as error:
        FeedCollector(limited).collect(context())
    assert error.value.code == "blocked_too_large"

    raised = FeedCollector(limited).collect(context(config={"max_bytes": 1_000_000}))
    assert [raw.title for raw in raised.items] == ["Galaxy S30"]


FEED_RELISTED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title><link>https://www.example.com</link>
<description>d</description>
<item><guid>old</guid><link>https://www.example.com/old</link><title>Best space heaters</title>
<pubDate>Thu, 01 Oct 2026 09:00:00 GMT</pubDate></item>
<item><guid>fresh</guid><link>https://www.example.com/fresh</link><title>New review</title>
<pubDate>Thu, 01 Oct 2026 10:00:00 GMT</pubDate></item>
<item><guid>known</guid><link>https://www.example.com/known</link><title>Seen already</title>
<pubDate>Thu, 01 Oct 2026 11:00:00 GMT</pubDate></item>
<item><guid>edited</guid><link>https://www.example.com/edited</link><title>Edited page</title>
<pubDate>Thu, 01 Oct 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""


def article(published: str, modified: str | None = None) -> bytes:
    tags = f'<meta property="article:published_time" content="{published}">'
    if modified:
        tags += f'<meta property="article:modified_time" content="{modified}">'
    return f"<html><head>{tags}</head><body><p>text</p></body></html>".encode()


def relisting_site(pages: dict[str, bytes], seen: list[str]) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/feed.xml":
            return httpx.Response(
                200, headers={"content-type": "application/rss+xml"}, content=FEED_RELISTED
            )
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=pages[request.url.path]
        )

    return mock_fetcher(handler)


def test_page_date_gives_a_relisted_post_its_own_earlier_date() -> None:
    seen: list[str] = []
    pages = {
        "/old": article("2025-03-01T09:00:00+00:00"),
        "/fresh": article("2026-10-01T10:00:00+00:00"),  # the feed is right: unchanged
        "/edited": article("2026-10-01T14:00:00+00:00"),  # later than the feed: never forward
    }

    result = FeedCollector(relisting_site(pages, seen)).collect(
        context(
            config={"page_date": True},
            known_ids=frozenset({stable_key("known")}),
        )
    )

    dates = {item.stable_id: item.published_at for item in result.items}
    assert dates["old"] == datetime(2025, 3, 1, 9, 0, tzinfo=UTC)
    assert dates["fresh"] == datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
    assert dates["known"] == datetime(2026, 10, 1, 11, 0, tzinfo=UTC)
    assert dates["edited"] == datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    assert "/known" not in seen  # a stored entry is not read again


def test_page_dates_are_read_only_for_sources_that_ask_and_within_the_limit() -> None:
    seen: list[str] = []
    pages = {"/old": article("2025-03-01T09:00:00+00:00")}

    plain = FeedCollector(relisting_site(pages, seen)).collect(context())
    assert all(
        item.published_at is not None and item.published_at.year == 2026 for item in plain.items
    )
    assert seen == ["/feed.xml"]

    limited = FeedCollector(relisting_site(pages, seen := [])).collect(
        context(config={"page_date": True, "enrich_limit": 1})
    )
    assert [p for p in seen if p != "/robots.txt"] == ["/feed.xml", "/old"]
    assert limited.items[0].published_at == datetime(2025, 3, 1, 9, 0, tzinfo=UTC)
