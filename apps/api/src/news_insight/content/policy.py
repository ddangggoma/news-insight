"""Storage-right policy (roadmap D9): what an item may keep, and for how long."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from news_insight.content.normalize import truncate
from news_insight.sources.enums import StorageRight

EXCERPT_MAX_CHARS = 500
FULLTEXT_TTL = timedelta(days=30)


@dataclass(frozen=True)
class StoredContent:
    summary: str | None
    body: str | None
    body_expires_at: datetime | None


def apply_storage_right(
    right: StorageRight | None, *, summary: str | None, body: str | None, now: datetime
) -> StoredContent:
    """`summary` and `body` must already be plain text."""
    if right is None or right is StorageRight.METADATA_ONLY:
        return StoredContent(summary=None, body=None, body_expires_at=None)
    excerpt_source = summary or body
    excerpt = truncate(excerpt_source, EXCERPT_MAX_CHARS) if excerpt_source else None
    if right is StorageRight.EXCERPT_ALLOWED:
        return StoredContent(summary=excerpt, body=None, body_expires_at=None)
    if right is StorageRight.FULLTEXT_TTL:
        expires = now + FULLTEXT_TTL if body else None
        return StoredContent(summary=excerpt, body=body, body_expires_at=expires)
    return StoredContent(summary=excerpt, body=body, body_expires_at=None)
