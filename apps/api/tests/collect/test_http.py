from datetime import UTC, datetime

import httpx
import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.http import conditional_headers, fetch_checked, request_headers
from tests.helpers import mock_fetcher, serving

URL = "https://www.example.com/feed.xml"
MIME = frozenset({"application/rss+xml"})


@pytest.mark.parametrize("status", [200, 304])
def test_success_statuses_are_returned(status: int) -> None:
    response = fetch_checked(serving(b"<rss/>", status=status), URL, allowed_mime=MIME)

    assert response.status_code == status


@pytest.mark.parametrize(("status", "code"), [(429, "rate_limited"), (503, "server_error")])
def test_transient_statuses_are_retryable(status: int, code: str) -> None:
    with pytest.raises(CollectorError) as error:
        fetch_checked(serving(b"", status=status), URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable, error.value.status_code) == (
        code,
        True,
        status,
    )


def test_client_errors_are_final() -> None:
    with pytest.raises(CollectorError) as error:
        fetch_checked(serving(b"", status=404), URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable) == ("http_404", False)


def test_timeouts_are_retryable() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(CollectorError) as error:
        fetch_checked(mock_fetcher(slow), URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable) == ("timeout", True)


def test_blocked_targets_are_final() -> None:
    with pytest.raises(CollectorError) as error:
        fetch_checked(serving(b""), "http://www.example.com/feed.xml", allowed_mime=MIME)

    assert (error.value.code, error.value.retryable) == ("blocked_scheme", False)


def test_conditional_headers_follow_context() -> None:
    context = CollectContext(
        endpoint_url=URL,
        config={},
        now=datetime(2026, 10, 3, tzinfo=UTC),
        etag='"v1"',
        last_modified="Thu, 01 Oct 2026 09:00:00 GMT",
    )

    assert conditional_headers(context) == {
        "If-None-Match": '"v1"',
        "If-Modified-Since": "Thu, 01 Oct 2026 09:00:00 GMT",
    }


def test_github_style_403_rate_limit_is_retryable() -> None:
    fetcher = serving(b"", status=403, headers={"x-ratelimit-remaining": "0"})

    with pytest.raises(CollectorError) as error:
        fetch_checked(fetcher, URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable) == ("rate_limited", True)


def test_request_headers_merge_credentials_and_validators() -> None:
    context = CollectContext(
        endpoint_url=URL,
        config={},
        now=datetime(2026, 10, 3, tzinfo=UTC),
        etag='"v1"',
        headers={"Authorization": "Bearer t"},
    )

    assert request_headers(context) == {"Authorization": "Bearer t", "If-None-Match": '"v1"'}


def test_stack_exchange_throttle_is_retryable_with_its_wait() -> None:
    body = (
        b'{"error_id":502,"error_message":"too many requests from this IP, '
        b'more requests available in 10830 seconds","error_name":"throttle_violation"}'
    )
    fetcher = serving(body, status=400, content_type="application/json")

    with pytest.raises(CollectorError) as error:
        fetch_checked(fetcher, URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable, error.value.retry_after) == (
        "rate_limited",
        True,
        10830,
    )


def test_other_400s_stay_final() -> None:
    fetcher = serving(
        b'{"error_name":"bad_parameter"}', status=400, content_type="application/json"
    )

    with pytest.raises(CollectorError) as error:
        fetch_checked(fetcher, URL, allowed_mime=MIME)

    assert (error.value.code, error.value.retryable) == ("http_400", False)


def test_retry_after_header_is_kept() -> None:
    fetcher = serving(b"", status=429, headers={"retry-after": "120"})

    with pytest.raises(CollectorError) as error:
        fetch_checked(fetcher, URL, allowed_mime=MIME)

    assert error.value.retry_after == 120
