import httpx
import pytest

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.checks import EXPECTED_MIME, check_network
from news_insight.sources.enums import AccessMethod
from tests.factories import build_source
from tests.helpers import mock_fetcher


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


def test_network_probe_sends_configured_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        ok = request.headers.get("X-Naver-Client-Id") == "id"
        return httpx.Response(
            200 if ok else 401, headers={"content-type": "application/json"}, content=b"{}"
        )

    monkeypatch.setenv("SOURCE_SECRET_NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("SOURCE_SECRET_NAVER_CLIENT_SECRET", "pw")
    source = build_source(
        access_method=AccessMethod.JSON_API,
        endpoint_url="https://openapi.naver.com/v1/search/news.json?query=x",
        official_domain="naver.com",
        config={
            "auth": {
                "scheme": "headers",
                "headers": {
                    "X-Naver-Client-Id": "NAVER_CLIENT_ID",
                    "X-Naver-Client-Secret": "NAVER_CLIENT_SECRET",
                },
            }
        },
    )

    assert check_network(source, mock_fetcher(handler)).passed
    assert seen[0].headers["X-Naver-Client-Secret"] == "pw"
