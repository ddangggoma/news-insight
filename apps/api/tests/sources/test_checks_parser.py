from datetime import UTC, datetime

import httpx

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import check_parser
from news_insight.sources.enums import AccessMethod
from tests.factories import build_source
from tests.parsers.test_feed_probe import item, rss

NOW = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


def fetcher_serving(content: bytes) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=content)

    return SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda host, port: ["93.184.216.34"],
        verify_peer=False,
    )


def test_parser_check_passes_for_healthy_feed() -> None:
    fetcher = fetcher_serving(rss(item(1), item(2), item(3)))

    assert check_parser(build_source(), fetcher, now=NOW).passed


def test_parser_check_never_lowers_minimum_below_three() -> None:
    fetcher = fetcher_serving(rss(item(1), item(2)))

    result = check_parser(build_source(config={"probe_min_items": 1}), fetcher, now=NOW)

    assert result.reasons == ["only 2 recent complete items (need 3)"]


def test_parser_check_honours_max_age_override() -> None:
    fetcher = fetcher_serving(rss(item(1), item(2), item(3)))

    result = check_parser(build_source(config={"probe_max_age_days": 1}), fetcher, now=NOW)

    assert not result.passed


def test_non_feed_access_methods_fail_closed() -> None:
    source = build_source(access_method=AccessMethod.GITHUB)

    result = check_parser(source, fetcher_serving(b""), now=NOW)

    assert result.reasons == ["no V3 parser probe for access method 'github' yet"]
