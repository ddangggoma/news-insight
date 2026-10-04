from news_insight.taxonomy.catalog import (
    FIELDS,
    IMPACT_KEYS,
    LABELS,
    SCOPE_KEYS,
    SIGNAL_TYPE_KEYS,
    THEME_KEYS,
    prompt_outline,
)
from news_insight.taxonomy.provisional import SIGNAL_MAP, THEME_MAP, provisional_labels


def test_v2_tree_has_twelve_technology_fields() -> None:
    assert len(FIELDS) == 12
    assert all(4 <= len(field.themes) <= 7 for field in FIELDS)
    assert len(THEME_KEYS) == 62
    assert all(key.split("__")[0] in {f.key for f in FIELDS} for key in THEME_KEYS)


def test_other_axes_have_no_business_axis() -> None:
    assert len(SIGNAL_TYPE_KEYS) == 10 and {"research", "launch", "regulation"} <= SIGNAL_TYPE_KEYS
    assert {"opportunity", "risk", "watch"} == IMPACT_KEYS
    assert {"dx", "dx_dependency", "excluded", "irrelevant"} == SCOPE_KEYS
    assert not any(key in LABELS for key in ("mx", "vd", "networks", "harman"))
    assert LABELS["connectivity__smart_home_iot"] == "스마트홈·IoT 연결"


def test_prompt_outline_lists_every_field_once() -> None:
    outline = prompt_outline()

    assert outline.count("\n") == 11
    assert "on_device_ai(온디바이스 AI·디바이스 AI 경험)" in outline


def test_provisional_map_covers_the_previous_tree() -> None:
    assert len(THEME_MAP) == 75
    assert all(target is None or target in THEME_KEYS for target in THEME_MAP.values())
    assert all(signal in SIGNAL_TYPE_KEYS for signal in SIGNAL_MAP.values())


def test_provisional_labels_fall_back_to_registry_themes() -> None:
    registry = {"matter": "connectivity__smart_home_iot", "oled": "display_av__display_panel"}

    direct = provisional_labels(["network_comms__fiveg_sixg"], ["matter"], registry)
    market = provisional_labels(["product_market__pricing_revenue"], ["matter", "oled"], registry)

    assert direct == (["connectivity__cellular_5g_6g"], None)
    assert market == (["connectivity__smart_home_iot", "display_av__display_panel"], "market")


def test_web_labels_match_the_catalog() -> None:
    from pathlib import Path

    from news_insight.taxonomy.catalog import TAXONOMY_REVISION

    web = (Path(__file__).resolve().parents[3] / "web" / "lib" / "taxonomy.ts").read_text()

    assert f'"{TAXONOMY_REVISION}"' in web
    assert all(f'"{key}":' in web for key in LABELS)
