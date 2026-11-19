from datetime import UTC, datetime

from news_insight.buzz.cluster import Post, bot_like, components, mark_bots, over_threshold
from news_insight.buzz.keys import author_of, clean_title, keys_for, platform_of

NOW = datetime(2026, 11, 19, 3, 0, tzinfo=UTC)


def post(
    i: int,
    title: str = "",
    *,
    author: str | None = None,
    links: list[str] | None = None,
    refs: list[str] | None = None,
    platform: str = "fediverse",
) -> Post:
    keys = keys_for(title, None, f"https://example.social/{i}") if title else None
    return Post(
        item_id=i,
        platform=platform,
        author=author_of(platform, author if author is not None else f"user{i}"),
        links=links or [],
        refs=refs if refs is not None else (keys.refs if keys else []),
        signature=keys.signature if keys else [],
        bands=keys.bands if keys else [],
        first_seen_at=NOW,
    )


def test_platform_families_fold_instances_and_entry_points() -> None:
    assert platform_of("Mastodon gGmbH", "activitypub") == "fediverse"
    assert platform_of("Fosstodon", "activitypub") == "fediverse"
    assert platform_of("social.kernel.org", "activitypub") == "fediverse"
    assert platform_of("Algolia (HN Search)", "json_api") == "hn"
    assert platform_of("Y Combinator", "feed") == "hn"
    assert platform_of("V2EX 程序员", "json_api") == "v2ex"
    assert platform_of("Meta Platforms", "crawler") == "threads"
    assert platform_of("DEV Community", "json_api") == "dev community"


def test_titles_lose_links_tags_and_mentions() -> None:
    # Mastodon titles split URLs after the scheme ("https:// techlensmedia.com/…")
    assert clean_title("Big outage at #AWS today https:// status.aws/x @ops@hachyderm.io !") == (
        "Big outage at today !"
    )
    assert author_of("fediverse", "@EUVD_Bot") == "fediverse:euvd_bot"
    assert author_of("hn", None) is None


def test_bot_names_and_bridges() -> None:
    assert bot_like("fediverse:euvd_bot")
    assert bot_like("fediverse:tecnoblog.net@web.brid.gy")
    assert bot_like("fediverse:newsbot@example.org")
    assert not bot_like("fediverse:robotics_fan")
    assert not bot_like("hn:abbot")


def test_feed_accounts_are_marked_by_volume() -> None:
    posts = [post(i, author="techwire") for i in range(20)] + [post(99, author="alice")]
    assert mark_bots(posts) == {"fediverse:techwire"}
    assert [p.bot for p in posts][-2:] == [True, False]


def test_posts_join_by_link_reference_or_close_title() -> None:
    title = "Rust 2.0 released with a new borrow checker and async closures"
    posts = [
        post(1, links=["k-article"]),
        post(2, links=["k-article", "k-own"]),
        post(3, "See github.com/acme/turbo for the code", refs=["github:acme/turbo"]),
        post(4, "turbo is out", refs=["github:acme/turbo"]),
        post(5, title),
        post(6, title + " (finally)"),
        post(7, "Completely unrelated thoughts about my garden and the weather"),
    ]
    groups = sorted(sorted(posts[i].item_id for i in g) for g in components(posts))
    assert groups == [[1, 2], [3, 4], [5, 6]]


def test_bot_titles_never_join_by_text() -> None:
    template = "CVE-2026-1 Critical (9.1) A vulnerability was found in a widely used product"
    posts = [post(1, template, refs=[]), post(2, template.replace("-1 ", "-2 "), refs=[])]
    for p in posts:
        p.bot = True
    assert components(posts) == []


def test_threshold() -> None:
    assert over_threshold(3, 2, 1.5)
    assert not over_threshold(3, 1, 1.5)  # one platform needs more people and heat
    assert not over_threshold(2, 2, 9.0)
    assert over_threshold(5, 1, 3.0)
    assert not over_threshold(5, 1, 2.9)
