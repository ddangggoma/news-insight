import httpx

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import EXPECTED_MIME, check_network
from news_insight.sources.enums import AccessMethod
from tests.factories import build_source


def fetcher_returning(status: int, content_type: str) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"content-type": content_type}, content=b"<rss/>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SafeFetcher(
        client=client, resolver=lambda host, port: ["93.184.216.34"], verify_peer=False
    )


def test_every_access_method_declares_expected_mime() -> None:
    assert set(EXPECTED_MIME) == set(AccessMethod)


def test_network_check_passes_for_feed_mime() -> None:
    result = check_network(build_source(), fetcher_returning(200, "application/rss+xml"))

    assert result.passed, result.reasons
    assert result.metrics["status"] == 200
    assert result.metrics["content_type"] == "application/rss+xml"


def test_network_check_reports_blocked_mime() -> None:
    result = check_network(build_source(), fetcher_returning(200, "text/html"))

    assert not result.passed
    assert result.metrics["error"] == "mime"


def test_network_check_fails_on_non_200() -> None:
    result = check_network(build_source(), fetcher_returning(404, "text/html"))

    assert result.reasons == ["unexpected HTTP status 404"]
