from collections.abc import Callable

import httpx
import pytest

from news_insight.net.safe_fetch import FetchBlocked, FetchFailed, SafeFetcher

PUBLIC_IP = "93.184.216.34"
Handler = Callable[[httpx.Request], httpx.Response]


def public_resolver(host: str, port: int) -> list[str]:
    return [PUBLIC_IP]


def make_fetcher(
    handler: Handler,
    *,
    resolver: Callable[[str, int], list[str]] = public_resolver,
    verify_peer: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
) -> SafeFetcher:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return SafeFetcher(
        client=client, resolver=resolver, verify_peer=verify_peer, max_bytes=max_bytes
    )


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=b"<rss/>")


class FakeStream:
    def __init__(self, address: str) -> None:
        self.address = address

    def get_extra_info(self, info: str) -> tuple[str, int] | None:
        return (self.address, 443) if info == "server_addr" else None


def test_fetches_public_https_resource() -> None:
    response = make_fetcher(ok).fetch("https://example.com/feed")

    assert response.status_code == 200
    assert response.content == b"<rss/>"
    assert response.content_type == "application/rss+xml"
    assert response.redirects == ()


def test_sends_identifying_user_agent() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return ok(request)

    make_fetcher(handler).fetch("https://example.com/feed")

    assert seen[0].startswith("DailyITIntelligenceBot/")


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://example.com/feed", "scheme"),
        ("https://user:pw@example.com/feed", "userinfo"),
        ("https://example.com:8443/feed", "port"),
    ],
)
def test_rejects_unsafe_urls(url: str, code: str) -> None:
    with pytest.raises(FetchBlocked) as error:
        make_fetcher(ok).fetch(url)

    assert error.value.code == code


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.5",
        "127.0.0.1",
        "169.254.169.254",
        "192.168.1.10",
        "100.64.0.1",
        "::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
    ],
)
def test_rejects_non_public_resolution(address: str) -> None:
    fetcher = make_fetcher(ok, resolver=lambda host, port: [address])

    with pytest.raises(FetchBlocked) as error:
        fetcher.fetch("https://example.com/feed")

    assert error.value.code == "private_address"


def test_rejects_when_any_resolved_address_is_private() -> None:
    fetcher = make_fetcher(ok, resolver=lambda host, port: [PUBLIC_IP, "10.0.0.1"])

    with pytest.raises(FetchBlocked):
        fetcher.fetch("https://example.com/feed")


def test_unresolvable_host_fails() -> None:
    def resolver(host: str, port: int) -> list[str]:
        raise OSError("nodename nor servname provided")

    with pytest.raises(FetchFailed) as error:
        make_fetcher(ok, resolver=resolver).fetch("https://example.com/feed")

    assert error.value.code == "dns"


def redirect_chain(hops: dict[str, str]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in hops:
            return httpx.Response(302, headers={"location": hops[request.url.path]})
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"done")

    return handler


def test_follows_up_to_three_redirects() -> None:
    fetcher = make_fetcher(redirect_chain({"/a": "/b", "/b": "/c", "/c": "/d"}))

    response = fetcher.fetch("https://example.com/a")

    assert response.content == b"done"
    assert response.url == "https://example.com/d"
    assert response.redirects == (
        "https://example.com/b",
        "https://example.com/c",
        "https://example.com/d",
    )


def test_rejects_fourth_redirect() -> None:
    fetcher = make_fetcher(redirect_chain({"/a": "/b", "/b": "/c", "/c": "/d", "/d": "/e"}))

    with pytest.raises(FetchBlocked) as error:
        fetcher.fetch("https://example.com/a")

    assert error.value.code == "too_many_redirects"


def test_revalidates_every_redirect_hop() -> None:
    def resolver(host: str, port: int) -> list[str]:
        return ["10.0.0.1"] if host == "internal.example" else [PUBLIC_IP]

    fetcher = make_fetcher(redirect_chain({"/a": "https://internal.example/x"}), resolver=resolver)

    with pytest.raises(FetchBlocked) as error:
        fetcher.fetch("https://example.com/a")

    assert error.value.code == "private_address"


def test_redirect_without_location_fails() -> None:
    fetcher = make_fetcher(lambda request: httpx.Response(302))

    with pytest.raises(FetchFailed) as error:
        fetcher.fetch("https://example.com/a")

    assert error.value.code == "bad_redirect"


def test_rejects_unexpected_mime() -> None:
    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, content=b""
        )

    with pytest.raises(FetchBlocked) as error:
        make_fetcher(html).fetch(
            "https://example.com/feed", allowed_mime=frozenset({"application/rss+xml"})
        )

    assert error.value.code == "mime"


def test_rejects_declared_oversized_body() -> None:
    fetcher = make_fetcher(lambda request: httpx.Response(200, content=b"x" * 2000), max_bytes=1000)

    with pytest.raises(FetchBlocked) as error:
        fetcher.fetch("https://example.com/big")

    assert error.value.code == "too_large"


def test_rejects_streamed_oversized_body_without_content_length() -> None:
    def chunked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=iter([b"a" * 600, b"b" * 600]))

    with pytest.raises(FetchBlocked) as error:
        make_fetcher(chunked, max_bytes=1000).fetch("https://example.com/big")

    assert error.value.code == "too_large"


def test_peer_verification_blocks_rebinding_to_private_address() -> None:
    def rebound(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"secret", extensions={"network_stream": FakeStream("10.0.0.9")}
        )

    with pytest.raises(FetchBlocked) as error:
        make_fetcher(rebound, verify_peer=True).fetch("https://example.com/feed")

    assert error.value.code == "private_address"


def test_peer_verification_requires_known_peer() -> None:
    with pytest.raises(FetchBlocked) as error:
        make_fetcher(ok, verify_peer=True).fetch("https://example.com/feed")

    assert error.value.code == "peer_address"


def test_peer_verification_accepts_public_peer() -> None:
    def public(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"ok", extensions={"network_stream": FakeStream(PUBLIC_IP)}
        )

    assert make_fetcher(public, verify_peer=True).fetch("https://example.com/").content == b"ok"


def test_timeout_is_reported_as_failure() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(FetchFailed) as error:
        make_fetcher(slow).fetch("https://example.com/feed")

    assert error.value.code == "timeout"
