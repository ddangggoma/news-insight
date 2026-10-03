from datetime import UTC, datetime

from news_insight.parsers.feed_probe import extract_items, probe_feed

NOW = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)
RECENT = "Thu, 01 Oct 2026 09:00:00 GMT"
STALE = "Mon, 01 Jun 2026 09:00:00 GMT"


def rss(*items: dict[str, str]) -> bytes:
    body = ""
    for item in items:
        title = f"<title>{item['title']}</title>" if item.get("title") else ""
        body += (
            f"<item><guid>{item['guid']}</guid><link>{item['link']}</link>{title}"
            f"<pubDate>{item['date']}</pubDate></item>"
        )
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
        f"<link>https://example.com</link><description>d</description>{body}</channel></rss>"
    ).encode()


def item(n: int, date: str = RECENT, title: str = "Title") -> dict[str, str]:
    return {
        "guid": f"id-{n}",
        "link": f"https://example.com/{n}",
        "title": f"{title} {n}",
        "date": date,
    }


def test_three_complete_recent_items_pass() -> None:
    result = probe_feed(rss(item(1), item(2), item(3)), now=NOW)

    assert result.passed, result.reasons
    assert result.metrics == {"entries": 3, "complete": 3, "recent": 3}


def test_items_missing_required_fields_do_not_count() -> None:
    incomplete = {"guid": "id-3", "link": "https://example.com/3", "title": "", "date": RECENT}

    result = probe_feed(rss(item(1), item(2), incomplete), now=NOW)

    assert result.reasons == ["only 2 recent complete items (need 3)"]


def test_stale_items_do_not_count() -> None:
    result = probe_feed(rss(item(1), item(2), item(3, date=STALE)), now=NOW)

    assert not result.passed
    assert result.metrics["recent"] == 2


def test_atom_feed_is_supported() -> None:
    entries = "".join(
        f'<entry><id>urn:{n}</id><title>A {n}</title><link href="https://example.com/{n}"/>'
        f"<updated>2026-10-01T09:00:00Z</updated></entry>"
        for n in range(3)
    )
    atom = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>t</title><id>urn:feed</id>'
        f"<updated>2026-10-01T09:00:00Z</updated>{entries}</feed>"
    ).encode()

    assert probe_feed(atom, now=NOW).passed


def test_garbage_is_rejected() -> None:
    result = probe_feed(b"definitely not a feed", now=NOW)

    assert result.reasons[0].startswith("feed could not be parsed")


def test_extract_items_returns_normalized_fields() -> None:
    [first] = extract_items(rss(item(7)))

    assert first.stable_id == "id-7"
    assert first.url == "https://example.com/7"
    assert first.title == "Title 7"
    assert first.published_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
