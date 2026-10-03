"""SSRF-safe HTTP fetcher shared by source validation (V2) and collectors.

Safety layers: https-only on port 443, no URL credentials, every resolved address must be
public, every redirect hop is re-validated (max 3), the connected peer address is re-checked
to defeat DNS rebinding, MIME allow-list, and a streamed byte cap.
"""

import ipaddress
import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import TracebackType

import httpx

from news_insight import __version__
from news_insight.config import Settings

Resolver = Callable[[str, int], list[str]]
DEFAULT_USER_AGENT = f"DailyITIntelligenceBot/{__version__}"
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
CROSS_HOST_SAFE_HEADERS = frozenset({"user-agent", "accept", "if-none-match", "if-modified-since"})


def _cross_host_headers(headers: dict[str, str]) -> dict[str, str]:
    """Never forward credentials (or any non-essential header) to a different host."""
    return {
        name: value for name, value in headers.items() if name.lower() in CROSS_HOST_SAFE_HEADERS
    }


class FetchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FetchBlocked(FetchError):
    """Refused by a safety policy."""


class FetchFailed(FetchError):
    """Could not be completed (DNS, timeout, transport, malformed redirect)."""


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def assert_public_ip(raw: str) -> None:
    address = ipaddress.ip_address(raw.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if not address.is_global or address.is_multicast:
        raise FetchBlocked("private_address", f"refusing non-public address {raw}")


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    content_type: str
    redirects: tuple[str, ...]
    elapsed_ms: int


class SafeFetcher:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Resolver = system_resolver,
        timeout_seconds: float = 15.0,
        max_redirects: int = 3,
        max_bytes: int = 5 * 1024 * 1024,
        verify_peer: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds), follow_redirects=False, trust_env=False
        )
        self._resolver = resolver
        self._max_redirects = max_redirects
        self._max_bytes = max_bytes
        self._verify_peer = verify_peer
        self._user_agent = user_agent

    @classmethod
    def from_settings(cls, settings: Settings) -> "SafeFetcher":
        return cls(
            timeout_seconds=settings.fetch_timeout_seconds,
            max_redirects=settings.fetch_max_redirects,
            max_bytes=settings.fetch_max_bytes,
        )

    def __enter__(self) -> "SafeFetcher":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch(
        self,
        url: str,
        *,
        allowed_mime: frozenset[str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResponse:
        started = time.monotonic()
        request_headers = {"User-Agent": self._user_agent, **(headers or {})}
        origin_host = httpx.URL(url).host
        current = url
        redirects: list[str] = []
        for _ in range(self._max_redirects + 1):
            self._validate_target(current)
            try:
                with self._client.stream("GET", current, headers=request_headers) as response:
                    self._check_peer(response)
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchFailed(
                                "bad_redirect", f"redirect without Location: {current}"
                            )
                        current = str(response.url.join(location))
                        redirects.append(current)
                        if httpx.URL(current).host != origin_host:
                            request_headers = _cross_host_headers(request_headers)
                        continue
                    content_type = (
                        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    )
                    if (
                        allowed_mime is not None
                        and response.status_code == 200
                        and content_type not in allowed_mime
                    ):
                        raise FetchBlocked("mime", f"unexpected content type '{content_type}'")
                    body = self._read_limited(response)
                    return FetchResponse(
                        url=current,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        content=body,
                        content_type=content_type,
                        redirects=tuple(redirects),
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                    )
            except httpx.TimeoutException as exc:
                raise FetchFailed("timeout", f"timed out fetching {current}") from exc
            except httpx.TransportError as exc:
                raise FetchFailed(
                    "transport", f"transport error fetching {current}: {exc}"
                ) from exc
        raise FetchBlocked("too_many_redirects", f"more than {self._max_redirects} redirects")

    def _validate_target(self, url: str) -> None:
        parts = httpx.URL(url)
        if parts.scheme != "https":
            raise FetchBlocked("scheme", f"only https is allowed: {url}")
        if parts.userinfo:
            raise FetchBlocked("userinfo", "credentials in URLs are not allowed")
        host = parts.host
        if not host:
            raise FetchBlocked("host", f"missing host: {url}")
        port = parts.port or 443
        if port != 443:
            raise FetchBlocked("port", f"only port 443 is allowed: {url}")
        try:
            addresses = self._resolver(host, port)
        except OSError as exc:
            raise FetchFailed("dns", f"cannot resolve {host}") from exc
        if not addresses:
            raise FetchFailed("dns", f"no addresses for {host}")
        for address in addresses:
            assert_public_ip(address)

    def _check_peer(self, response: httpx.Response) -> None:
        if not self._verify_peer:
            return
        stream = response.extensions.get("network_stream")
        server_addr = stream.get_extra_info("server_addr") if stream is not None else None
        if not server_addr:
            raise FetchBlocked("peer_address", "cannot confirm the connected peer address")
        assert_public_ip(str(server_addr[0]))

    def _read_limited(self, response: httpx.Response) -> bytes:
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max_bytes:
            raise FetchBlocked("too_large", f"declared size {declared} exceeds {self._max_bytes}")
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > self._max_bytes:
                raise FetchBlocked("too_large", f"response exceeds {self._max_bytes} bytes")
        return bytes(body)
