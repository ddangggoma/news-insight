from news_insight.content.dedup import (
    dedup_keys,
    normalize_url,
    shared_link,
    text_links,
    titles_agree,
    url_key,
)

ARTICLE = "Pentagon stops using Anthropic AI tools after blacklisting company, BBC told"


def keys(title: str, summary: str | None = None, url: str = "https://example.com/a"):
    return dedup_keys(canonical=url, title=title, summary=summary, body=None, link=None)


def test_url_key_ignores_tracking_scheme_and_www() -> None:
    plain = "https://www.bbc.co.uk/news/articles/c5j9x9pr0240o"
    tracked = "http://bbc.co.uk/news/articles/c5j9x9pr0240o/?at_campaign=rss&at_medium=RSS"
    assert normalize_url(tracked) == "bbc.co.uk/news/articles/c5j9x9pr0240o"
    assert url_key(plain) == url_key(tracked)
    assert url_key("https://example.com/a?id=1") != url_key("https://example.com/a?id=2")


def test_text_key_ignores_links_hashtags_and_punctuation() -> None:
    post = keys(ARTICLE, f"{ARTICLE} https://www. bbc.co.uk/news/articles/c5j9x9pr0240o #AI")
    copy = keys(ARTICLE.upper() + "!", f"{ARTICLE} @someone")
    assert post.text is not None and post.text == copy.text


def test_short_pages_get_no_text_or_title_key() -> None:
    """2026-10-10: "Home" at JEDEC and at ICO shared a content hash."""
    home = keys("Home")
    assert home.text is None and home.title is None


def test_same_title_needs_agreeing_bodies() -> None:
    android = keys(
        "PUBG MOBILE | US | Darkpool Chart Explorer",
        "PUBG MOBILE on Android in US: Top Free Games ranking history. Explore recent movement",
    )
    ios = keys(
        "PUBG MOBILE | US | Darkpool Chart Explorer",
        "PUBG MOBILE on iOS in US: Top Free Games ranking history. Explore recent movement",
    )
    social = keys(ARTICLE)  # a post with no real body
    article = keys(ARTICLE, "The US Department of Defense has stopped using the tools of ...")
    assert android.title == ios.title
    assert not titles_agree(android.lead, android.lead_title, ios.lead, ios.lead_title)
    assert titles_agree(social.lead, social.lead_title, article.lead, article.lead_title)


def test_shared_link_skips_hashtags_mentions_and_own_host() -> None:
    html = (
        '<p><span class="h-card"><a href="https://mastodon.social/@bbc" class="u-url mention">'
        '@bbc</a></span> Pentagon drops Anthropic <a href="https://www.bbc.co.uk/news/articles/x1?'
        'at_campaign=rss" rel="nofollow"><span class="invisible">https://www.</span>bbc.co.uk/'
        '</a> <a href="https://mastodon.social/tags/ai" class="mention hashtag">#ai</a></p>'
    )
    assert shared_link(html, post_url="https://mastodon.social/@x/1") == (
        "https://www.bbc.co.uk/news/articles/x1?at_campaign=rss"
    )
    assert shared_link("<p>no link</p>", post_url="https://mastodon.social/@x/1") is None


def test_text_links_glue_split_mastodon_spans() -> None:
    text = (
        "JNTC plans to invest. Source: DigiTimes Asia https://www. digitimes.com/news/"
        "a20261008VL 223/jntc-glass.htm more words"
    )
    found = text_links(text)
    assert "https://www.digitimes.com/news/a20261008VL223/jntc-glass.htm" in found


def test_malformed_urls_do_not_raise() -> None:
    assert normalize_url("https://[broken/path") == "https://[broken/path"
    html = '<a href="https://[broken">x</a> <a href="https://ok.example/a">y</a>'
    assert shared_link(html, post_url="https://mastodon.social/@x/1") == "https://ok.example/a"
