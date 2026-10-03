from collections.abc import Callable

import httpx

from news_insight.net.safe_fetch import SafeFetcher

PUBLIC_IP = "93.184.216.34"


def mock_fetcher(handler: Callable[[httpx.Request], httpx.Response]) -> SafeFetcher:
    return SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda host, port: [PUBLIC_IP],
        verify_peer=False,
    )


def serving(
    content: bytes,
    *,
    status: int = 200,
    content_type: str = "application/rss+xml",
    headers: dict[str, str] | None = None,
    seen: list[httpx.Request] | None = None,
) -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(
            status, headers={"content-type": content_type, **(headers or {})}, content=content
        )

    return mock_fetcher(handler)
