import json
from datetime import UTC, datetime
from typing import Any

import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.json_api import JsonApiCollector
from tests.helpers import serving

NOW = datetime(2026, 10, 3, tzinfo=UTC)
OCT_1_0900 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
CONFIG: dict[str, Any] = {
    "list_path": "data.items",
    "fields": {
        "url": "html_url",
        "title": "name",
        "summary": "description",
        "published_at": "created_at",
        "author": "owner.login",
    },
}
RECORDS = [
    {
        "id": 101,
        "html_url": "/r/101",
        "name": "On-device LLM runtime",
        "description": "fast",
        "created_at": "2026-10-01T09:00:00Z",
        "owner": {"login": "kim"},
    },
    {
        "id": 102,
        "html_url": "https://www.example.com/r/102",
        "name": "NPU kernels",
        "created_at": 1790845200,
    },
]


def payload(records: list[dict[str, Any]]) -> bytes:
    return json.dumps({"data": {"items": records}}).encode()


def collect(content: bytes, *, status: int = 200, **config: Any) -> Any:
    context = CollectContext(
        endpoint_url="https://www.example.com/api/repos", config={**CONFIG, **config}, now=NOW
    )
    fetcher = serving(content, status=status, content_type="application/json")
    return JsonApiCollector(fetcher).collect(context)


def test_maps_records_with_nested_fields_and_relative_urls() -> None:
    first, second = collect(payload(RECORDS)).items

    assert (first.stable_id, first.url, first.author) == (
        "101",
        "https://www.example.com/r/101",
        "kim",
    )
    assert (first.summary, first.published_at) == ("fast", OCT_1_0900)
    assert (second.stable_id, second.published_at) == ("102", OCT_1_0900)


def test_missing_list_is_drift() -> None:
    with pytest.raises(CollectorError) as error:
        collect(payload(RECORDS), list_path="data.missing")

    assert error.value.code == "selector_drift"


def test_majority_incomplete_records_signal_drift() -> None:
    broken = [{"id": n, "html_url": f"/r/{n}"} for n in (2, 3)]

    with pytest.raises(CollectorError) as error:
        collect(payload(RECORDS[:1] + broken))

    assert error.value.code == "selector_drift"


def test_invalid_json_is_a_parse_error() -> None:
    with pytest.raises(CollectorError) as error:
        collect(b"{oops")

    assert (error.value.code, error.value.retryable) == ("parse_error", False)


def test_not_modified() -> None:
    assert collect(b"", status=304).not_modified is True


def test_item_limit_caps_records() -> None:
    assert len(collect(payload(RECORDS), item_limit=1).items) == 1
