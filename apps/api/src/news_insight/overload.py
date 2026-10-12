"""Bound the API's concurrent requests (2026-10-12).

Every handler is synchronous and shares a small database pool, so a burst of page loads used to
queue inside the API until requests took 15-20 s and the web server's callers gave up. This
middleware admits at most `API_MAX_INFLIGHT` requests at once; the rest wait up to
`API_QUEUE_SECONDS` for a slot and are then refused with 503 and Retry-After, which the web
server and Caddy turn into a "try again shortly" page instead of a hang. 0 turns it off (tests,
host dev). Health checks and session lookups are cheap and always pass, so a busy API never looks
dead to Docker or logs everyone out.
"""

import asyncio
import json
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("news_insight.http")

EXEMPT_PATHS = frozenset({"/api/health", "/api/admin/accounts/session"})
RETRY_AFTER_SECONDS = 5


class OverloadGuard:
    def __init__(self, app: ASGIApp, *, max_inflight: int, queue_seconds: float) -> None:
        self.app = app
        self.max_inflight = max_inflight
        self.queue_seconds = queue_seconds
        self._slots: asyncio.Semaphore | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.max_inflight <= 0 or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        if self._slots is None:
            self._slots = asyncio.Semaphore(self.max_inflight)
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=self.queue_seconds)
        except TimeoutError:
            log.warning("overloaded", extra={"path": scope["path"], "status": 503})
            await _busy(send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self._slots.release()


async def _busy(send: Send) -> None:
    body = json.dumps({"detail": "서버가 바쁩니다. 잠시 후 다시 시도하세요."}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", str(RETRY_AFTER_SECONDS).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
