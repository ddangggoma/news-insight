import json
from datetime import UTC, datetime
from typing import Any

import httpx
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


def collect_records(records: list[dict[str, Any]], **config: Any) -> Any:
    context = CollectContext(
        endpoint_url="https://www.example.com/api",
        config={"list_path": "data.items", **config},
        now=NOW,
    )
    fetcher = serving(payload(records), content_type="application/json")
    return JsonApiCollector(fetcher).collect(context)


def test_field_alternatives_take_the_first_non_empty_value() -> None:
    record = {"id": 1, "html_url": "https://www.example.com/r/1", "name": "", "tag_name": "v1.0"}

    [item] = collect_records(
        [record], fields={"url": "html_url", "title": ["name", "tag_name"]}
    ).items

    assert item.title == "v1.0"


def test_url_template_fills_missing_links() -> None:
    record = {
        "post": {
            "uri": "at://did:plc:abc/app.bsky.feed.post/3kq",
            "author": {"handle": "bsky.app"},
            "record": {"text": "hello world", "createdAt": "2026-10-01T09:00:00Z"},
        }
    }

    [item] = collect_records(
        [record],
        fields={
            "id": "post.uri",
            "url": [],
            "title": "post.record.text",
            "published_at": "post.record.createdAt",
        },
        url_template="https://bsky.app/profile/{post.author.handle}/post/{post.uri|last}",
    ).items

    assert item.url == "https://bsky.app/profile/bsky.app/post/3kq"
    assert item.stable_id == "at://did:plc:abc/app.bsky.feed.post/3kq"


def test_title_limit_shortens_html_posts() -> None:
    record = {"id": 1, "url": "https://www.example.com/p/1", "title": "<p>" + "가" * 200 + "</p>"}

    [item] = collect_records([record], title_limit=50).items

    assert len(item.title) == 50
    assert "<p>" not in item.title


def test_metrics_are_mapped_to_integers() -> None:
    record = {
        "id": 1,
        "url": "https://www.example.com/p/1",
        "title": "repo",
        "stargazers_count": 16168,
        "archived": False,
    }

    [item] = collect_records(
        [record], metrics={"stars": "stargazers_count", "flag": "archived", "gone": "missing"}
    ).items

    assert item.metrics == {"stars": 16168}


def test_credential_headers_are_sent() -> None:
    seen: list[httpx.Request] = []
    context = CollectContext(
        endpoint_url="https://www.example.com/api",
        config=CONFIG,
        now=NOW,
        headers={"Authorization": "Bearer t0k"},
    )

    JsonApiCollector(serving(payload(RECORDS), content_type="application/json", seen=seen)).collect(
        context
    )

    assert seen[0].headers["authorization"] == "Bearer t0k"
