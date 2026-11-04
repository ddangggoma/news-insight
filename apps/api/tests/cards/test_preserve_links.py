"""Pieces of a split link are no facts (2026-10-27 audit K07: 49 cards ended in "5ae-ba")."""

from news_insight.cards.preserve import missing_facts
from news_insight.cards.schemas import CardDraft, CardInput


def lost(title: str, title_ko: str) -> list[str]:
    card = CardInput(id=1, title=title, source="Mastodon", language="en", excerpt=None)
    draft = CardDraft(id=1, title_ko=title_ko, summary_ko=[], keywords=["k"])
    return missing_facts(card, draft)


def test_the_cut_off_end_of_an_id_after_a_split_link_is_not_a_fact() -> None:
    title = (
        "What if AI prefers CVs written by AI?… # technology # thegeektribune "
        "https://www. ft.com/content/b7671d34-878e-4 5ae-ba…"
    )
    assert lost(title, "AI가 AI가 쓴 이력서를 선호한다면") == []


def test_a_query_split_off_a_link_is_not_a_fact() -> None:
    title = "# Linux all the wayyyyy https:// youtube.com/shorts/8kQVsdFa3kQ ?si=AbSIBBDx0IqtugSJ"
    assert lost(title, "리눅스 만세") == []


def test_numbers_and_models_next_to_a_link_are_still_facts() -> None:
    title = "Nvidia ships H100 successor https://www. example.com/news/ results up 35%"
    assert lost(title, "엔비디아 후속 칩 출시") == ["H100", "35%"]


def test_ids_and_slugs_split_off_a_link_are_not_facts() -> None:
    posts = [
        "RE: https:// mastodon.social/@harold/117520 944856607407 # NovaScotia Premier's office",
        "# AI # tech https:// apnews.com/article/norway-ai-g lasses-ban-be20dbd949ce0580238",
    ]
    assert [lost(post, "캐나다 노바스코샤 주정부 소식") for post in posts] == [[], []]


def test_mentions_are_not_facts() -> None:
    title = "@ Susan_calvin @ grumble209 I was chatting with my older neighbor yesterday"
    assert lost(title, "이웃과 나눈 대화") == []
