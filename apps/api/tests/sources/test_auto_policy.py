from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.auto_policy import check_auto_policy, robots_verdict
from news_insight.sources.enums import AccessMethod, StorageRight, ValidationStage
from news_insight.sources.models import Source
from news_insight.sources.service import climb
from tests.factories import build_source
from tests.helpers import mock_fetcher

ITEM = (
    "<item><title>{0}</title><link>https://www.example.com/{0}</link><pubDate>{1}</pubDate></item>"
)
FEED = (
    '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
    + "".join(ITEM.format(n, f"Sat, 03 Oct 2026 0{i}:00:00 GMT") for i, n in enumerate("abc", 1))
    + "</channel></rss>"
).encode()


def site(robots: httpx.Response | None) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            if robots is None:
                raise httpx.ConnectError("down")
            return robots
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=FEED)

    return mock_fetcher(handler)


def robots(text: str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/plain"}, content=text.encode())


def unreviewed(**overrides: object) -> Source:
    return build_source(**{"terms_url": None, "storage_right": None, **overrides})


def test_missing_robots_allows_and_disallow_rules_block() -> None:
    url = "https://www.example.com/feed.xml"

    assert robots_verdict(site(httpx.Response(404)), url)[0] is True
    assert robots_verdict(site(robots("User-agent: *\nDisallow: /private")), url)[0] is True
    assert robots_verdict(site(robots("User-agent: *\nDisallow: /")), url)[0] is False
    assert (
        robots_verdict(site(robots("User-agent: DailyITIntelligenceBot\nDisallow: /feed")), url)[0]
        is False
    )
    assert robots_verdict(site(None), url)[0] is False
    assert robots_verdict(site(httpx.Response(503)), url)[0] is False


def test_public_feed_is_auto_approved_with_excerpt_storage() -> None:
    result = check_auto_policy(unreviewed(), site(httpx.Response(404)))

    assert result.passed
    assert result.metrics["auto_approved"] is True
    assert result.metrics["storage_right"] == "excerpt_allowed"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"access_method": AccessMethod.CRAWLER}, "selectors or config.mode=auto"),
        ({"config": {"manual_review": True}}, "manual_review"),
        ({"config": {"auth": {"secret": "NOT_SET_ANYWHERE"}}}, "SOURCE_SECRET_NOT_SET_ANYWHERE"),
        ({"storage_right": StorageRight.FULLTEXT_PERMITTED}, "at most excerpt"),
    ],
)
def test_auto_approval_refusals(overrides: dict[str, object], reason: str) -> None:
    result = check_auto_policy(unreviewed(**overrides), site(httpx.Response(404)))

    assert not result.passed
    assert any(reason in text for text in result.reasons)


@pytest.mark.db
def test_climb_uses_auto_policy_without_terms_and_sets_storage(db_session: Session) -> None:
    source = unreviewed()
    db_session.add(source)
    db_session.flush()

    events = climb(
        db_session,
        source,
        fetcher=site(httpx.Response(404)),
        now=datetime(2026, 10, 3, 12, tzinfo=UTC),
    )

    assert [event.stage for event in events] == [
        ValidationStage.V0,
        ValidationStage.V1,
        ValidationStage.V2,
        ValidationStage.V3,
    ]
    assert source.validation_stage is ValidationStage.V3
    assert source.storage_right is StorageRight.EXCERPT_ALLOWED
    assert events[1].metrics["auto_approved"] is True


def test_documented_apis_skip_robots_and_auto_crawlers_respect_it() -> None:
    blocked = site(robots("User-agent: *\nDisallow: /"))

    api = check_auto_policy(unreviewed(access_method=AccessMethod.JSON_API), blocked)
    crawler = check_auto_policy(
        unreviewed(access_method=AccessMethod.CRAWLER, config={"mode": "auto"}), blocked
    )
    allowed_crawler = check_auto_policy(
        unreviewed(access_method=AccessMethod.CRAWLER, config={"mode": "auto"}),
        site(httpx.Response(404)),
    )

    assert api.passed and api.metrics["robots"].startswith("not applicable")
    assert not crawler.passed and "disallows" in crawler.reasons[0]
    assert allowed_crawler.passed


@pytest.mark.parametrize(
    "rules",
    [
        robots("User-agent: *\nDisallow: /"),
        robots("User-agent: DailyITIntelligenceBot\nDisallow: /feed"),
        None,  # robots.txt unreachable (Samsung newsroom timeouts, 2026-10-05)
    ],
)
def test_feeds_are_read_as_a_feed_reader_but_sitemaps_keep_robots(
    rules: httpx.Response | None,
) -> None:
    feed = check_auto_policy(unreviewed(), site(rules))
    sitemap = check_auto_policy(unreviewed(access_method=AccessMethod.SITEMAP), site(rules))

    assert feed.passed and feed.metrics["robots"].startswith("feed reader:")
    assert not sitemap.passed


def test_velog_hydration_mode_keeps_robots_gate() -> None:
    source = unreviewed(access_method=AccessMethod.CRAWLER, config={"mode": "velog"})
    assert check_auto_policy(source, site(robots("User-agent: *\nAllow: /"))).passed
    assert not check_auto_policy(source, site(robots("User-agent: *\nDisallow: /"))).passed
