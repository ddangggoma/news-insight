from datetime import UTC, datetime, timedelta

import pytest

from news_insight.content.policy import EXCERPT_MAX_CHARS, FULLTEXT_TTL, apply_storage_right
from news_insight.sources.enums import StorageRight

NOW = datetime(2026, 10, 3, tzinfo=UTC)
LONG = "가" * 800


@pytest.mark.parametrize("right", [None, StorageRight.METADATA_ONLY])
def test_metadata_only_keeps_no_text(right: StorageRight | None) -> None:
    stored = apply_storage_right(right, summary="s", body="b", now=NOW)

    assert (stored.summary, stored.body, stored.body_expires_at) == (None, None, None)


def test_excerpt_is_capped_at_500_chars() -> None:
    stored = apply_storage_right(StorageRight.EXCERPT_ALLOWED, summary=LONG, body="full", now=NOW)

    assert stored.summary is not None
    assert len(stored.summary) == EXCERPT_MAX_CHARS
    assert stored.body is None


def test_excerpt_falls_back_to_body() -> None:
    stored = apply_storage_right(
        StorageRight.EXCERPT_ALLOWED, summary=None, body="body text", now=NOW
    )

    assert stored.summary == "body text"


def test_fulltext_ttl_expires_after_30_days() -> None:
    stored = apply_storage_right(StorageRight.FULLTEXT_TTL, summary="s", body="full text", now=NOW)

    assert stored.body == "full text"
    assert stored.body_expires_at == NOW + FULLTEXT_TTL == NOW + timedelta(days=30)


def test_fulltext_permitted_keeps_body_without_expiry() -> None:
    stored = apply_storage_right(
        StorageRight.FULLTEXT_PERMITTED, summary=None, body="full", now=NOW
    )

    assert (stored.body, stored.body_expires_at) == ("full", None)
