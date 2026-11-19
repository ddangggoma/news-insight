import json
from datetime import UTC, datetime, timedelta

import pytest

from news_insight.collect.contracts import CollectContext, CollectorError
from news_insight.collect.crawler import CrawlerCollector
from tests.helpers import serving

NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)
SEARCH = "https://www.threads.com/search?q=humanoid%20robot&serp_type=default"


TEXT = "Humanoid robots are folding laundry now\nmore"


def post(code="DfAbc1", *, hours_ago=2, text=TEXT, **extra):
    info = {
        "direct_reply_count": 3,
        "repost_count": 13,
        "quote_count": 1,
        "reshare_count": 6,
        "link_preview_attachment": None,
        "reply_to_author": None,
    }
    info.update(extra.pop("info", {}))
    return {
        "code": code,
        "pk": "3700000000000000001",
        "taken_at": int((NOW - timedelta(hours=hours_ago)).timestamp()),
        "user": {"username": "robot.fan_1", "pk": "63442731218"},
        "caption": {"text": text},
        "like_count": 120,
        "like_and_view_counts_disabled": False,
        "text_post_app_info": info,
        **extra,
    }


def page(posts, *, container="searchResults"):
    edges = [{"node": {"thread": {"thread_items": [{"post": item}]}}} for item in posts]
    data = {
        "require": [
            [
                "ScheduledServerJS",
                "handle",
                None,
                [{"__bbox": {"result": {"data": {container: {"edges": edges}}}}}],
            ]
        ]
    }
    return (
        '<html><script type="application/json" data-sjs>{"other": 1}</script>'
        f'<script type="application/json" data-sjs>{json.dumps(data)}</script></html>'
    ).encode()


def collect(body, *, url=SEARCH, config=None, fetcher=None):
    fetcher = fetcher or serving(body, content_type="text/html")
    return CrawlerCollector(fetcher).collect(
        CollectContext(endpoint_url=url, config={"mode": "threads", **(config or {})}, now=NOW)
    )


def test_reads_posts_and_reaction_counts_from_embedded_json():
    [item] = collect(page([post()])).items
    assert item.stable_id == "DfAbc1"
    assert item.url == "https://www.threads.com/@robot.fan_1/post/DfAbc1"
    assert item.title == "Humanoid robots are folding laundry now"
    assert item.summary.startswith("Humanoid robots are folding laundry now")
    assert item.author == "robot.fan_1"
    assert item.published_at == NOW - timedelta(hours=2)
    assert item.body is None
    assert item.metrics == {"likes": 120, "replies": 3, "reposts": 13, "quotes": 1, "reshares": 6}


def test_profile_pages_embed_media_data():
    assert len(collect(page([post()], container="mediaData")).items) == 1


def test_hidden_like_counts_are_not_reported_as_zero():
    [item] = collect(page([post(like_and_view_counts_disabled=True)])).items
    assert "likes" not in item.metrics
    assert item.metrics["reposts"] == 13


def test_shared_link_is_the_preview_or_first_external_url():
    preview = post(info={"link_preview_attachment": {"url": "https://example.com/a"}})
    text = post("DfAbc2", text="Read this https://techcrunch.com/story. Also @threads")
    own = post("DfAbc3", text="see https://www.threads.com/@x/post/1")
    items = {item.stable_id: item for item in collect(page([preview, text, own])).items}
    assert items["DfAbc1"].link == "https://example.com/a"
    assert items["DfAbc2"].link == "https://techcrunch.com/story"
    assert items["DfAbc3"].link is None


def test_skips_replies_wordless_media_old_and_repeated_posts():
    posts = [
        post(),
        post(),
        post("reply", info={"reply_to_author": {"username": "someone"}}),
        post("image", text=""),
        post("old", hours_ago=24 * 30),
    ]
    assert [item.stable_id for item in collect(page(posts)).items] == ["DfAbc1"]


def test_age_window_follows_config():
    old = post("old", hours_ago=24 * 30)
    assert collect(page([old]), config={"max_age_days": 60}).items[0].stable_id == "old"


def test_empty_result_list_is_a_successful_empty_run():
    result = collect(page([]))
    assert result.items == []
    assert result.status_code == 200


def test_page_without_post_data_backs_off_the_provider():
    with pytest.raises(CollectorError) as error:
        collect(b"<html><title>Log in</title><script>window.x=1</script></html>")
    assert error.value.code == "rate_limited"
    assert error.value.retryable
    assert error.value.retry_after == 3600


def test_sends_navigation_headers_with_our_own_user_agent():
    seen = []
    collect(None, fetcher=serving(page([post()]), content_type="text/html", seen=seen))
    sent = seen[-1].headers
    assert sent["sec-fetch-mode"] == "navigate"
    assert sent["sec-fetch-dest"] == "document"
    assert "Mozilla" not in sent["user-agent"]
    assert "cookie" not in sent
