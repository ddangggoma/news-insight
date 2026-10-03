"""Collector contract shared by every access-method adapter."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

DEFAULT_ITEM_LIMIT = 50
MAX_ITEM_LIMIT = 200


@dataclass(frozen=True)
class RawItem:
    stable_id: str
    url: str
    title: str
    published_at: datetime | None = None
    author: str | None = None
    summary: str | None = None
    body: str | None = None


@dataclass(frozen=True)
class CollectContext:
    endpoint_url: str
    config: dict[str, Any]
    now: datetime
    etag: str | None = None
    last_modified: str | None = None
    last_success_at: datetime | None = None

    @property
    def item_limit(self) -> int:
        try:
            value = int(self.config.get("item_limit", DEFAULT_ITEM_LIMIT))
        except (TypeError, ValueError):
            value = DEFAULT_ITEM_LIMIT
        return max(1, min(value, MAX_ITEM_LIMIT))


@dataclass(frozen=True)
class CollectResult:
    items: list[RawItem]
    status_code: int
    elapsed_ms: int
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
    incomplete: int = 0


class CollectorError(Exception):
    """A collection attempt failed; `retryable` chooses backoff over dead letter."""

    def __init__(
        self, code: str, message: str, *, retryable: bool, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code


class Collector(Protocol):
    def collect(self, context: CollectContext) -> CollectResult: ...


def majority_incomplete(incomplete: int, examined: int) -> bool:
    """Drift signal: more than half of the examined records lost a required field."""
    return examined > 0 and incomplete * 2 > examined
