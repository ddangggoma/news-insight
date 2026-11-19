"""Official Threads API presets against recorded-shape responses (synthetic posts and users)."""

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from news_insight.collect.contracts import CollectContext
from news_insight.collect.json_api import JsonApiCollector
from news_insight.collect.presets import THREADS_FIELDS, effective_config
from news_insight.collect.threads import collect_threads
from tests.helpers import serving

NOW = datetime(2026, 11, 19, 6, 0, tzinfo=UTC)
SEARCH = "https://graph.threads.net/v1.0/keyword_search?q=humanoid%20robot&search_type=TOP"


def post(shortcode: str, text: str | None, **extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": f"1800000000000{len(shortcode):04d}",
        "shortcode": shortcode,
        "media_type": "TEXT_POST",
        "permalink": f"https://www.threads.net/@robot.news/post/{shortcode}",
        "timestamp": "2026-11-18T09:30:00+0000",
        "username": "robot.news",
        "is_reply": False,
    }
    if text is not None:
        record["text"] = text
    return {**record, **extra}


def collect(
    records: list[dict[str, Any]],
    *,
    preset: str = "threads_keyword_search",
    url: str = SEARCH,
    seen: list[httpx.Request] | None = None,
) -> Any:
    body = json.dumps({"data": records}).encode()
    context = CollectContext(
        endpoint_url=url,
        config=effective_config({"preset": preset, "auth": {"secret": "THREADS_TOKEN"}}),
        now=NOW,
        headers={"Authorization": "Bearer test-token"},
    )
    fetcher = serving(body, content_type="application/json", seen=seen)
    return JsonApiCollector(fetcher).collect(context)


def test_keyword_search_asks_for_documented_fields_with_a_bearer_token() -> None:
    seen: list[httpx.Request] = []

    collect([post("DAbc1", "Humanoid robots in factories")], seen=seen)

    [request] = seen
    assert request.url.params["q"] == "humanoid robot"
    assert request.url.params["search_type"] == "TOP"
    assert request.url.params["fields"] == THREADS_FIELDS
    assert "access_token" not in request.url.params  # never in a URL, a log or an error
    assert request.headers["authorization"] == "Bearer test-token"


def test_posts_map_like_the_crawler() -> None:
    text = "Humanoid robots in factories\n\nA long thread " + "x" * 800
    [item] = collect(
        [post("DAbc1", text, link_attachment_url="https://www.example.com/robots")]
    ).items

    assert item.stable_id == "DAbc1"
    assert item.url == "https://www.threads.com/@robot.news/post/DAbc1"
    assert item.title == "Humanoid robots in factories"
    assert item.author == "robot.news"
    assert item.published_at == datetime(2026, 11, 18, 9, 30, tzinfo=UTC)
    assert item.summary is not None and len(item.summary) <= 500
    assert item.link == "https://www.example.com/robots"
    assert item.metrics == {}  # the API documents no reaction counts on other users' posts


def test_replies_reposts_and_old_posts_are_left_out() -> None:
    records = [
        post("DKeep", "AI chips ship"),
        post("DReply", "agreed", is_reply=True),
        post("DRepost", None, media_type="REPOST_FACADE"),
        post("DOld", "Last month's news", timestamp="2026-10-01T09:00:00+0000"),
    ]

    result = collect(records)

    assert [item.stable_id for item in result.items] == ["DKeep"]
    assert result.incomplete == 0  # skipped records are not drift


def test_profile_posts_preset() -> None:
    url = "https://graph.threads.net/v1.0/profile_posts?username=robot.news"
    seen: list[httpx.Request] = []

    [item] = collect(
        [post("DProf1", "New robot hand")], preset="threads_profile_posts", url=url, seen=seen
    ).items

    assert seen[0].url.params["username"] == "robot.news"
    assert seen[0].url.params["fields"] == THREADS_FIELDS
    assert item.url == "https://www.threads.com/@robot.news/post/DProf1"


def test_api_and_crawler_agree_on_identity() -> None:
    """The same post seen by the crawler and the API is one item (same id and URL)."""
    page = {
        "searchResults": [
            {
                "code": "DAbc1",
                "taken_at": int(datetime(2026, 11, 18, 9, 30, tzinfo=UTC).timestamp()),
                "user": {"username": "robot.news"},
                "caption": {"text": "Humanoid robots in factories"},
            }
        ]
    }
    html = f'<script type="application/json">{json.dumps(page)}</script>'.encode()
    crawled = collect_threads(
        serving(html, content_type="text/html"),
        CollectContext(
            endpoint_url="https://www.threads.com/search?q=humanoid%20robot",
            config={"max_age_days": 14},
            now=NOW,
        ),
    ).items
    [api] = collect([post("DAbc1", "Humanoid robots in factories")]).items

    assert [(item.stable_id, item.url, item.title) for item in crawled] == [
        (api.stable_id, api.url, api.title)
    ]
