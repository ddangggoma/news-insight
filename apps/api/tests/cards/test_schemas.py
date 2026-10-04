from news_insight.cards.schemas import CardInput, parse_drafts

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
