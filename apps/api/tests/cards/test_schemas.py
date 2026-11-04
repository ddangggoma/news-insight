import pytest

from news_insight.cards.schemas import (
    CardInput,
    card_instructions,
    is_meta_sentence,
    parse_drafts,
)

INPUTS = [
    CardInput(
        id=1, title="Galaxy S30", source="The Verge", language="en", excerpt="Ships in March."
    ),
    CardInput(id=2, title="OLED", source="ETNews", language="ko", excerpt=None),
]


def test_drafts_keep_known_ids_and_drop_invented_summaries() -> None:
    raw = {
        "cards": [
            {
                "id": 1,
                "title_ko": "갤럭시 S30",
                "summary_ko": ["3월 출시", "", "a", "b"],
                "keywords": ["#삼성", "삼성", "갤럭시", "S30", "AI", "x", "y"],
            },
            {"id": 2, "title_ko": "OLED", "summary_ko": ["지어낸 요약"], "keywords": []},
            {"id": 9, "title_ko": "unknown", "summary_ko": [], "keywords": []},
            {"id": 1, "title_ko": "duplicate", "summary_ko": [], "keywords": []},
            {"id": 3},
        ]
    }

    drafts = parse_drafts(raw, INPUTS)

    assert set(drafts) == {1, 2}
    assert drafts[1].title_ko == "갤럭시 S30"
    assert drafts[1].summary_ko == ["3월 출시", "a", "b"]
    assert drafts[1].keywords == ["삼성", "갤럭시", "S30", "AI", "x"]
    assert drafts[2].summary_ko == []


def test_malformed_output_yields_nothing() -> None:
    assert parse_drafts(None, INPUTS) == {}
    assert parse_drafts({"cards": "nope"}, INPUTS) == {}


def test_classification_is_validated_against_the_taxonomy() -> None:
    raw = {
        "cards": [
            {
                "id": 1,
                "title_ko": "갤럭시 S30",
                "summary_ko": [],
                "keywords": [],
                "field": "platform_sw",
                "themes": [
                    "smartphone_compute",
                    "ai__on_device_ai",
                    "nope",
                    "platform_sw__device_os",
                ],
                "signal_type": "launch",
                "impact": "opportunity",
                "scope": "dx",
                "relevance": 140,
            },
            {
                "id": 2,
                "title_ko": "OLED",
                "summary_ko": [],
                "keywords": [],
                "field": "unknown",
                "themes": ["display_av__display_panel"],
                "signal_type": "boom",
                "impact": "boom",
                "scope": "maybe",
                "relevance": -5,
            },
        ]
    }

    drafts = parse_drafts(raw, INPUTS)

    first, second = drafts[1], drafts[2]
    assert first.themes == ["ai__on_device_ai", "platform_sw__device_os"]
    assert first.field == "ai"  # the primary field follows the first theme
    assert (first.signal_type, first.impact, first.scope, first.relevance) == (
        "launch",
        "opportunity",
        "dx",
        100,
    )
    assert second.field == "display_av"
    assert (second.signal_type, second.impact, second.scope, second.relevance) == (
        None,
        None,
        None,
        0,
    )


def test_summary_sentences_about_the_excerpt_are_dropped() -> None:
    """2026-11-04 audit: Haiku wrote "발췌에는 링크와 태그만 있다" as the summary of 968 cards."""
    raw = {
        "cards": [
            {
                "id": 1,
                "title_ko": "갤럭시 S30",
                "summary_ko": [
                    "3월에 출시된다. 구체적인 사양은 발췌에서 확인되지 않는다.",
                    "발췌에는 링크와 태그만 있고 본문 내용은 없다.",
                    "배터리는 5,000mAh다.",
                ],
            }
        ]
    }

    assert parse_drafts(raw, INPUTS)[1].summary_ko == ["3월에 출시된다.", "배터리는 5,000mAh다."]


def test_a_summary_with_nothing_but_commentary_is_empty() -> None:
    raw = {
        "cards": [
            {"id": 1, "title_ko": "갤럭시", "summary_ko": ["발췌문이 짧아 내용은 확인되지 않는다."]}
        ]
    }

    assert parse_drafts(raw, INPUTS)[1].summary_ko == []


@pytest.mark.parametrize(
    "sentence",
    [
        "GPU 가격이 20% 올랐다.",
        "원문 링크를 공유한 게시물이다.",  # about the post, not about missing text
        "제공된 API로 데이터를 가져온다.",
    ],
)
def test_ordinary_sentences_are_not_meta(sentence: str) -> None:
    assert not is_meta_sentence(sentence)


def test_card_prompt_asks_for_plain_style_and_dates_from_the_published_day() -> None:
    prompt = card_instructions()

    assert "'~다'체" in prompt
    assert "published" in prompt
    assert "excerpt 자체를 설명하지 않는다" in prompt


def test_published_day_reaches_the_engine_payload() -> None:
    card = CardInput(
        id=1, title="x", source="s", language="en", excerpt="y", published="2026-11-04"
    )

    assert card.model_dump(exclude_none=True)["published"] == "2026-11-04"
