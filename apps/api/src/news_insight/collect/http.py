"""Map SafeFetcher outcomes onto collector errors, and build conditional-request headers."""

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.net.safe_fetch import FetchBlocked, FetchFailed, FetchResponse, SafeFetcher


def conditional_headers(context: CollectContext) -> dict[str, str]:
    headers: dict[str, str] = {}
    if context.etag:
        headers["If-None-Match"] = context.etag
    if context.last_modified:
        headers["If-Modified-Since"] = context.last_modified
    return headers


def request_headers(context: CollectContext) -> dict[str, str]:
    """Credential headers resolved for the source, plus conditional-request validators."""
    return {**context.headers, **conditional_headers(context)}


def fetch_checked(
    fetcher: SafeFetcher,
    url: str,
    *,
    allowed_mime: frozenset[str],
    headers: dict[str, str] | None = None,
) -> FetchResponse:
    """Return 200/304 responses; raise CollectorError for everything else."""
    try:
        response = fetcher.fetch(url, allowed_mime=allowed_mime, headers=headers)
    except FetchFailed as exc:
        raise CollectorError(exc.code, str(exc), retryable=True) from exc
    except FetchBlocked as exc:
        raise CollectorError(f"blocked_{exc.code}", str(exc), retryable=False) from exc
    status = response.status_code
    if status in (200, 304):
        return response
    message = f"HTTP {status} from {url}"
    if status == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        raise CollectorError("rate_limited", message, retryable=True, status_code=status)
    if status == 429:
        raise CollectorError("rate_limited", message, retryable=True, status_code=status)
    if status >= 500:
        raise CollectorError("server_error", message, retryable=True, status_code=status)
    raise CollectorError(f"http_{status}", message, retryable=False, status_code=status)
