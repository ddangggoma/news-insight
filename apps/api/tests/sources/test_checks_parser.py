import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import check_parser
from news_insight.sources.enums import AccessMethod
from tests.factories import build_source
from tests.helpers import serving
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


def json_source(**config: Any) -> Any:
    return build_source(
        access_method=AccessMethod.JSON_API,
        endpoint_url="https://www.example.com/api",
        config={"list_path": "items", **config},
    )


def json_fetcher(*dates: str | None) -> SafeFetcher:
    records = [
        {"id": n, "url": f"https://www.example.com/{n}", "title": f"T{n}", "published_at": date}
        for n, date in enumerate(dates)
    ]
    return serving(json.dumps({"items": records}).encode(), content_type="application/json")


def test_json_sources_are_probed_through_their_collector() -> None:
    fetcher = json_fetcher(*["2026-10-01T09:00:00Z"] * 3)

    result = check_parser(json_source(), fetcher, now=NOW)

    assert result.passed, result.reasons
    assert result.metrics == {"items": 3, "dated": 3, "recent": 3}


def test_json_probe_requires_recent_dated_items() -> None:
    fetcher = json_fetcher("2026-10-01T09:00:00Z", None, "2026-01-01T00:00:00Z")

    result = check_parser(json_source(), fetcher, now=NOW)

    assert result.reasons == ["only 1 recent complete items (need 3)"]


def test_probe_reports_collector_errors() -> None:
    result = check_parser(json_source(list_path="missing"), json_fetcher("x"), now=NOW)

    assert result.reasons[0].startswith("selector_drift")


def test_probe_reports_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCE_SECRET_GITHUB_TOKEN", raising=False)
    source = json_source(auth={"secret": "GITHUB_TOKEN"})

    result = check_parser(source, json_fetcher(), now=NOW)

    assert "credential SOURCE_SECRET_GITHUB_TOKEN is not configured" in result.reasons


def test_github_observations_validate_rank_without_fake_publication_dates() -> None:
    source = build_source(
        access_method=AccessMethod.CRAWLER,
        config={"mode": "github_trending", "trending_period": "daily"},
    )
    page = b"".join(
        f'<article class="Box-row"><h2><a href="https://github.com/o/r{n}">repo</a></h2></article>'.encode()
        for n in range(3)
    )
    result = check_parser(source, serving(page, content_type="text/html"), now=NOW)
    assert result.passed, result.reasons
    assert result.metrics["date_semantics"] == "observation"


def test_github_observations_still_require_three_unique_identities() -> None:
    source = build_source(access_method=AccessMethod.CRAWLER, config={"mode": "github_trending"})
    page = (
        b'<article class="Box-row"><h2><a href="https://github.com/o/r">repo</a></h2></article>' * 3
    )
    assert not check_parser(source, serving(page, content_type="text/html"), now=NOW).passed
