"""Structured JSON logs and slow-request tracking (checklist OPS-1).

One `configure_logging(service)` call per process (API, Celery worker/beat, CLI). Every
record is a single JSON line with the service, the request id (API) and any `extra=` keys.
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
SLOW_KEY = "ops:slow_requests"
SLOW_SECONDS = 5.0
SLOW_KEEP_SECONDS = 24 * 3600
_STANDARD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = REQUEST_ID.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _STANDARD and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(service: str, *, level: int = logging.INFO) -> None:
    """Idempotent: replaces root handlers with one JSON stream handler."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # uvicorn installs its own plain-text handlers: route its errors (tracebacks included)
    # through the JSON handler instead (2026-10-05: 500s reached the log only as raw text)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.beat"):
        named = logging.getLogger(name)
        named.handlers[:] = []
        named.propagate = True


def record_slow_request(path: str, seconds: float, *, now: float | None = None) -> None:
    """Remember slow responses in Redis for the ops check (best effort)."""
    from news_insight.scheduling.redis_guards import get_redis

    stamp = now if now is not None else time.time()
    try:
        client = get_redis()
        client.zadd(SLOW_KEY, {f"{stamp:.3f} {path} {seconds:.2f}": stamp})
        client.zremrangebyscore(SLOW_KEY, 0, stamp - SLOW_KEEP_SECONDS)
    except Exception:  # noqa: BLE001 - metrics must never break a response
        logging.getLogger(__name__).debug("slow request not recorded", exc_info=True)


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Request id + one access line per API request; slow public/admin calls are recorded."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = REQUEST_ID.set(request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logging.getLogger("news_insight.http").exception(
                "unhandled error", extra={"method": request.method, "path": request.url.path}
            )
            raise
        finally:
            seconds = time.perf_counter() - started
            path = request.url.path
            if path != "/api/health":
                logging.getLogger("news_insight.http").info(
                    "request",
                    extra={
                        "method": request.method,
                        "path": path,
                        "status": status,
                        "ms": round(seconds * 1000),
                    },
                )
            if seconds >= SLOW_SECONDS and path.startswith("/api/"):
                record_slow_request(path, seconds)
            REQUEST_ID.reset(token)
