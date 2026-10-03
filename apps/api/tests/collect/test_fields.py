from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from news_insight.collect.fields import dotted_get, parse_datetime, text_or_none

OCT_1_0900 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-01T09:00:00Z", OCT_1_0900),
        ("2026-10-01", datetime(2026, 10, 1, tzinfo=UTC)),
        ("2026.10.01", datetime(2026, 10, 1, tzinfo=UTC)),
        (1790845200, OCT_1_0900),
        (1790845200000, OCT_1_0900),
        ("Thu, 01 Oct 2026 09:00:00 GMT", OCT_1_0900),
        ("not a date", None),
    ],
)
def test_parse_datetime_formats(value: Any, expected: datetime | None) -> None:
    assert parse_datetime(value) == expected


def test_naive_values_use_the_assumed_timezone() -> None:
    assert parse_datetime("2026.10.01 18:00", assume_tz=ZoneInfo("Asia/Seoul")) == OCT_1_0900


def test_dotted_get_walks_dicts_and_lists() -> None:
    payload = {"data": {"items": [{"owner": {"login": "kim"}}]}}

    assert dotted_get(payload, "data.items.0.owner.login") == "kim"
    assert dotted_get(payload, "data.missing.x") is None
    assert dotted_get(payload, "") is payload
    assert text_or_none({"nested": True}) is None
    assert text_or_none("  ") is None
