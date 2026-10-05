import json
from datetime import UTC, datetime

import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.crawler import CrawlerCollector
from tests.helpers import serving

NOW = datetime(2026, 10, 5, tzinfo=UTC)
POST = {
    "id": "post-1",
    "title": "Public post",
    "url_slug": "글 제목",
    "user": {"username": "author", "email": "private@example.com"},
    "released_at": "2026-10-04T12:00:00Z",
    "updated_at": "2026-10-05T00:00:00Z",
    "short_description": "Summary",
    "body": "Full body must not be stored",
    "likes": 12,
    "comments_count": 3,
}


def collect(posts=None, *, page=None):
    if page is None:
        chunk = "8:" + json.dumps(["$", "$L21", None, {"data": posts}]) + "\n"
        page = ("<script>self.__next_f.push(" + json.dumps([1, chunk]) + ")</script>").encode()
    return CrawlerCollector(serving(page, content_type="text/html")).collect(
        CollectContext(
            endpoint_url="https://velog.io/", config={"mode": "velog", "max_age_days": 30}, now=NOW
        )
    )


def test_reads_public_hydration_data_without_evaluating_javascript():
    [item] = collect([POST]).items
    assert item.stable_id == "post-1"
    assert item.url == "https://velog.io/@author/%EA%B8%80%20%EC%A0%9C%EB%AA%A9"
    assert item.published_at == datetime(2026, 10, 4, 12, tzinfo=UTC)
    assert item.author == "author"
    assert item.body is None
    assert item.metrics == {"likes": 12, "comments": 3}


def test_ignores_private_draft_and_old_posts():
    assert (
        collect(
            [
                POST,
                {**POST, "id": "private", "is_private": True},
                {**POST, "id": "draft", "is_temp": True},
                {**POST, "id": "old", "released_at": "2024-01-01T00:00:00Z"},
            ]
        )
        .items[0]
        .stable_id
        == "post-1"
    )
    assert len(collect([POST, {**POST, "id": "private", "is_private": True}]).items) == 1


def test_missing_publication_is_not_replaced_with_update_or_collection_time():
    assert collect([{**POST, "released_at": None}]).items == []


def test_drift_is_an_error_instead_of_successful_empty_page():
    with pytest.raises(CollectorError, match="selector_drift"):
        collect(page=b'<script>self.__next_f.push([1,"malformed"])</script>')


def test_repeated_hydration_records_have_one_identity():
    assert len(collect([POST, POST]).items) == 1


def test_conditional_response_does_not_require_a_hydration_page():
    result = CrawlerCollector(serving(b"", status=304, content_type="text/html")).collect(
        CollectContext(
            endpoint_url="https://velog.io/", config={"mode": "velog"}, now=NOW, etag="old"
        )
    )
    assert result.not_modified
    assert result.items == []
