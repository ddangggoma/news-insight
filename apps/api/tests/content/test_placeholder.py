"""Site placeholders are no text (2026-10-27 card audit K01) and boilerplate is no story (K08)."""

import pytest
from sqlalchemy import Text, cast, literal, select
from sqlalchemy.orm import Session

from news_insight.content.dedup import dedup_keys
from news_insight.content.placeholder import (
    has_text,
    is_placeholder,
    strip_boilerplate,
    usable_text,
)

PLACEHOLDERS = [
    None,
    "",
    "   ",
    "Comments",
    "comments",
    "None",
    "null",
    "N/A",
    "(",
    "...",
    "…",
    "robotics",
    "text-generation",
    "# infosec # cybersecurity",
    "#ai #ia #chatgpt #prompt #image",
    "Read more",
    "originally published at...",
    "(topic deleted by author) 1 post - 1 participant read full topic",
    "点击查看原文>",
    "여기를 눌러 링크를 확인하세요",
]
REAL = [
    "Samsung starts mass production of 12-layer HBM4",
    "삼성전자, HBM4 양산 시작",
    "삼성전자",  # one Korean word is still text
    "AIが業界を変える",
    "The official Python library for the OpenAI API",
    "Open-source home automation platform running on Python 3.",
    "Read more about the chip shortage hitting carmakers",
    "Comments are closed on this article, which covers the new export rules in detail.",
    "出处说明",
]


@pytest.mark.parametrize("text", PLACEHOLDERS)
def test_placeholders_are_no_text(text: str | None) -> None:
    assert is_placeholder(text)
    assert usable_text(text) is None


@pytest.mark.parametrize("text", REAL)
def test_real_text_is_kept(text: str) -> None:
    assert not is_placeholder(text)
    assert usable_text(text) == text


def test_usable_text_falls_through_to_the_body() -> None:
    assert usable_text("Comments", "The body of the article.") == "The body of the article."
    assert usable_text(None, "None") is None
    assert usable_text("Real summary", "Real body") == "Real summary"


@pytest.mark.db
def test_sql_and_python_agree(db_session: Session) -> None:
    """`has_text` (card queues, donor selection) must judge exactly like `is_placeholder`."""

    def text(value: str | None):  # type: ignore[no-untyped-def]
        return cast(literal(value), Text)

    for value in [*PLACEHOLDERS, *REAL]:
        sql = db_session.scalar(select(has_text(text(value), text(None))))
        assert bool(sql) is (not is_placeholder(value)), value
    assert db_session.scalar(select(has_text(text("Comments"), text("Body text")))) is True
    assert db_session.scalar(select(has_text(text(None), text(None)))) is False


def test_strip_boilerplate_removes_label_tail_and_hashtags() -> None:
    assert (
        strip_boilerplate(
            "Source: BleepingComputer Read: https://x.io/a More cyber news: https://y"
        )
        .replace("https://x.io/a", "")
        .strip()
        == ""
    )
    assert "Apple" not in strip_boilerplate("so # Apple wins")
    assert strip_boilerplate("Hacker group breaks into the ministry") == (
        "Hacker group breaks into the ministry"
    )


def keys(title: str, summary: str | None = None):
    return dedup_keys(
        canonical="https://mastodon.social/@x/1", title=title, summary=summary, body=None, link=None
    )


def test_source_label_posts_about_different_articles_share_no_key() -> None:
    """K08: 14 posts of one bot, each sharing another article, copied one card."""
    a = "Source: BleepingComputer Read: https://www. bleepingcomputer.com/news/security/a-1/"
    b = "Source: BleepingComputer Read: https://www. bleepingcomputer.com/news/security/b-2/"
    tail = " More cyber news: https:// cyzo.io/news?utm_source=social # Cyzo # Cybersecurity"
    first, second = keys(a, a + tail), keys(b, b + tail)
    assert first.text is None and second.text is None
    assert first.title is None and second.title is None


def test_a_truncated_source_label_title_gets_no_title_key() -> None:
    title = "Source: Be Connected - a trusted Australian government site for older people…"
    assert keys(title, title + " # Cyzo").title is None


def test_tag_lists_and_publisher_labels_get_no_key() -> None:
    """K08: wacoca/AppBank posts keep only the publisher and its tag list once the URL
    extraction has taken the title; every one of them had the same key."""
    tags = "AppBank # # GAMING # Android # Game # GameNews # games # GamingNews # iOS # iPhone"
    post = (
        "https://www. wacoca.com/games/1480672/ トーガと銃で変化する迷路を駆け抜ける8bit風 | "
        + tags
    )
    other = (
        "https://www. wacoca.com/games/1481058/ 各プレイヤーが1色だけ担当する協力マッチ3 | " + tags
    )
    assert keys(post, post).text is None
    assert keys(other, other).text is None
    assert keys("# InfoSec # CyberSecurity # Malware # Ransomware # Phishing").text is None


def test_real_posts_keep_their_text_key() -> None:
    post = "Voxtral 3 brings a voice agent SDK and speech models in 50+ languages # ai"
    copy = "Voxtral 3 brings a voice agent SDK and speech models in 50+ languages # AI # LLM"
    first, second = keys(post, post), keys(post, copy)
    assert first.text is not None and first.title is not None
    assert first.title == second.title
