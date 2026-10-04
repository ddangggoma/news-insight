from news_insight.cards.schemas import (
    CardInput,
    LabelInput,
    card_batch_schema,
    card_instructions,
    label_batch_schema,
    label_instructions,
    parse_drafts,
    parse_labels,
)
from news_insight.classify.taxonomy import Axis, get_taxonomy

TAXONOMY = get_taxonomy()

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


def test_labels_are_kept_when_known_and_dropped_when_not() -> None:
    raw = {
        "cards": [
            {
                "id": 1,
                "title_ko": "갤럭시 S30",
                "summary_ko": [],
                "keywords": [],
                "fields": ["ai", "quantum_gravity", "display", "AI", "network", "camera"],
                "products": ["phone", "toaster"],
                "impact": "opportunity",
            },
            {
                "id": 2,
                "title_ko": "OLED",
                "summary_ko": [],
                "keywords": [],
                "fields": "display",
                "products": None,
                "impact": "great",
            },
        ]
    }

    drafts = parse_drafts(raw, INPUTS, TAXONOMY)

    assert drafts[1].labels == {
        Axis.FIELD: ["ai", "display", "network"],
        Axis.PRODUCT: ["phone"],
        Axis.IMPACT: ["opportunity"],
    }
    assert drafts[2].labels == {Axis.FIELD: [], Axis.PRODUCT: [], Axis.IMPACT: []}


def test_cards_without_labels_stay_valid() -> None:
    raw = {"cards": [{"id": 1, "title_ko": "갤럭시", "summary_ko": [], "keywords": []}]}

    drafts = parse_drafts(raw, INPUTS, TAXONOMY)

    assert drafts[1].title_ko == "갤럭시" and drafts[1].labels is None


def test_schema_and_instructions_come_from_the_taxonomy() -> None:
    schema = card_batch_schema(TAXONOMY)
    card = schema["properties"]["cards"]["items"]

    assert card["properties"]["fields"]["items"]["enum"] == list(TAXONOMY.keys(Axis.FIELD))
    assert card["properties"]["fields"]["maxItems"] == 3
    assert card["properties"]["impact"]["enum"] == ["opportunity", "risk", "watch"]
    assert {"fields", "products", "impact"} <= set(card["required"])
    assert "genai_service: 생성형 AI 서비스" in card_instructions(TAXONOMY)


def test_label_only_batches_for_backfill() -> None:
    inputs = [LabelInput(id=5, title="폴드 8 공개", summary=["얇아졌다"])]
    raw = {
        "labels": [
            {"id": 5, "fields": ["display"], "products": ["foldable"], "impact": "watch"},
            {"id": 6, "fields": ["ai"], "products": [], "impact": "risk"},
            {"id": 5, "fields": ["ai"], "products": [], "impact": "risk"},
            "junk",
        ]
    }

    labels = parse_labels(raw, inputs, TAXONOMY)

    assert labels == {
        5: {Axis.FIELD: ["display"], Axis.PRODUCT: ["foldable"], Axis.IMPACT: ["watch"]}
    }
    assert parse_labels({"labels": "x"}, inputs, TAXONOMY) == {}
    assert "labels" in label_batch_schema(TAXONOMY)["required"]
    assert "impact" in label_instructions(TAXONOMY)
