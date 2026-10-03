from datetime import UTC, datetime
from typing import Any

import pytest

from news_insight.collect.contracts import CollectContext, majority_incomplete

NOW = datetime(2026, 10, 3, tzinfo=UTC)


@pytest.mark.parametrize(("configured", "expected"), [(None, 50), (500, 200), (0, 1), ("many", 50)])
def test_item_limit_is_clamped(configured: Any, expected: int) -> None:
    config = {} if configured is None else {"item_limit": configured}
    context = CollectContext(endpoint_url="https://example.com/feed", config=config, now=NOW)

    assert context.item_limit == expected


def test_majority_incomplete_needs_more_than_half() -> None:
    assert majority_incomplete(2, 3) is True
    assert majority_incomplete(1, 2) is False
    assert majority_incomplete(0, 0) is False
