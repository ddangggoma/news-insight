from news_insight.content.normalize import (
    canonical_url,
    clean_text,
    content_hash,
    html_to_text,
    stable_key,
    truncate,
)


def test_canonical_url_strips_tracking_and_fragment() -> None:
    url = "HTTPS://Example.COM:443/news/a/?utm_source=x&b=2&fbclid=z&a=1#comments"

    assert canonical_url(url) == "https://example.com/news/a?a=1&b=2"


def test_canonical_url_keeps_root_and_non_default_port() -> None:
    assert canonical_url("https://example.com") == "https://example.com/"
    assert canonical_url("http://example.com:80/x") == "http://example.com/x"
    assert canonical_url("https://example.com:8443/x") == "https://example.com:8443/x"


def test_html_to_text_drops_markup_scripts_and_entities() -> None:
    assert html_to_text("<p>Hello&nbsp;<b>world</b></p><script>track()</script>") == "Hello world"
    assert html_to_text("AT&amp;T  ships\n6G") == "AT&T ships 6G"
    assert html_to_text(None) == ""


def test_content_hash_ignores_markup_and_whitespace() -> None:
    assert content_hash("<p>Galaxy  S30</p>", None) == content_hash("Galaxy S30", "")


def test_content_hash_changes_with_text() -> None:
    assert content_hash("Galaxy S30", "128GB") != content_hash("Galaxy S30", "256GB")


def test_stable_key_hashes_overlong_ids() -> None:
    assert stable_key(" id-1 ") == "id-1"
    hashed = stable_key("x" * 600)
    assert hashed.startswith("sha256:")
    assert len(hashed) == 71


def test_truncate_and_clean_text() -> None:
    assert truncate("abcdef", 4) == "abc…"
    assert truncate("abc", 4) == "abc"
    assert clean_text("<p> </p>") is None
    assert clean_text("<b>Long title</b>", limit=6) == "Long…"
