from news_insight.taxonomy.catalog import (
    BUSINESS_KEYS,
    FIELDS,
    IMPACT_KEYS,
    LABELS,
    SCOPE_KEYS,
    THEME_KEYS,
    prompt_outline,
)


def test_tree_has_fifteen_fields_and_seventy_five_unique_themes() -> None:
    assert len(FIELDS) == 15
    assert all(len(field.themes) == 5 for field in FIELDS)
    assert len(THEME_KEYS) == 75
    assert all(key.split("__")[0] in {f.key for f in FIELDS} for key in THEME_KEYS)


def test_other_axes() -> None:
    assert {"mx", "vd", "da", "networks", "health", "harman"} == BUSINESS_KEYS
    assert {"opportunity", "risk", "watch"} == IMPACT_KEYS
    assert {"dx", "dx_dependency", "excluded", "irrelevant"} == SCOPE_KEYS
    assert LABELS["display_media__oled_microled"] == "OLED·MicroLED"


def test_prompt_outline_lists_every_theme_once() -> None:
    outline = prompt_outline()

    assert outline.count("\n") == 14
    assert "edge_ai(온디바이스·엣지 AI)" in outline
