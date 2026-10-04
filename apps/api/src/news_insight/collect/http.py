"""Map SafeFetcher outcomes onto collector errors, and build conditional-request headers."""

import json
import re

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
        raise CollectorError(
            "rate_limited",
            message,
            retryable=True,
            status_code=status,
            retry_after=_seconds(response.headers.get("retry-after")),
        )
    throttle = _api_throttle(response.content) if status == 400 else None
    if throttle is not None:
        raise CollectorError(
            "rate_limited",
            f"{message}: {throttle[0]}",
            retryable=True,
            status_code=status,
            retry_after=throttle[1],
        )
    if status >= 500:
        raise CollectorError("server_error", message, retryable=True, status_code=status)
    raise CollectorError(f"http_{status}", message, retryable=False, status_code=status)


def _seconds(value: str | None) -> int | None:
    return int(value) if value and value.strip().isdigit() else None


def _api_throttle(body: bytes) -> tuple[str, int | None] | None:
    """Stack Exchange answers quota exhaustion with HTTP 400 and error_name throttle_violation."""
    try:
        data = json.loads(body[:2000])
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("error_name") != "throttle_violation":
        return None
    text = str(data.get("error_message", ""))
    wait = re.search(r"(\d+) seconds", text)
    return text, int(wait.group(1)) if wait else None
