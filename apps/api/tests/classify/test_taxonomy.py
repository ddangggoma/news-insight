from pathlib import Path

import pytest
import yaml

from news_insight.classify.taxonomy import (
    DEFAULT_TAXONOMY_PATH,
    Axis,
    TaxonomyError,
    load_taxonomy,
)

MINIMAL: dict[str, object] = {
    "version": 1,
    "revision": 3,
    "rules": {
        "max_fields": 2,
        "max_products": 1,
        "guidance": ["반도체 자산 투자는 다루지 않는다."],
    },
    "axes": {
        "field": {
            "nodes": [
                {"key": "ai", "label": "온디바이스 AI·모델", "description": "모델 경량화"},
                {"key": "display", "label": "디스플레이", "description": "패널"},
                {"key": "network", "label": "통신·네트워크", "description": "5G·6G"},
            ],
        },
        "product": {
            "nodes": [
                {"key": "phone", "label": "스마트폰", "description": "바형 스마트폰"},
                {"key": "foldable", "label": "폴더블", "description": "접는 폰"},
            ],
        },
        "impact": {
            "nodes": [
                {"key": "opportunity", "label": "기회", "description": "기회"},
                {"key": "risk", "label": "위험", "description": "위험"},
                {"key": "watch", "label": "관찰", "description": "관찰"},
            ],
        },
    },
}


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "taxonomy.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_shipped_taxonomy_is_the_finalized_v1() -> None:
    taxonomy = load_taxonomy(DEFAULT_TAXONOMY_PATH)

    assert taxonomy.revision >= 1
    assert len(taxonomy.keys(Axis.FIELD)) == 23
    assert len(taxonomy.keys(Axis.PRODUCT)) == 18
    assert taxonomy.keys(Axis.IMPACT) == ("opportunity", "risk", "watch")
    assert {"genai_service", "smarthome", "quantum"} <= set(taxonomy.keys(Axis.FIELD))
    assert {"earbuds_audio", "signage", "camera_drone"} <= set(taxonomy.keys(Axis.PRODUCT))
    assert not {"smart_ring", "game_device"} & set(taxonomy.keys(Axis.PRODUCT))
    assert taxonomy.label(Axis.FIELD, "ai") == "온디바이스 AI·모델"
    assert taxonomy.label(Axis.PRODUCT, "home_robot_iot") == "홈로봇·IoT"
    assert (taxonomy.max_labels(Axis.FIELD), taxonomy.max_labels(Axis.PRODUCT)) == (3, 3)
    assert taxonomy.max_labels(Axis.IMPACT) == 1
    assert all(node.description for node in taxonomy.nodes(Axis.FIELD))


def test_pick_drops_unknown_keys_duplicates_and_caps(tmp_path: Path) -> None:
    taxonomy = load_taxonomy(write(tmp_path, MINIMAL))

    assert taxonomy.pick(Axis.FIELD, [" AI ", "ai", "quantum", "display", "network"]) == [
        "ai",
        "display",
    ]
    assert taxonomy.pick(Axis.PRODUCT, [7, None, "phone", "foldable"]) == ["phone"]
    assert taxonomy.pick(Axis.IMPACT, ["boom"]) == []
    assert taxonomy.pick(Axis.IMPACT, ["risk", "watch"]) == ["risk"]
    assert taxonomy.label(Axis.FIELD, "quantum") is None


def test_prompt_lists_every_key_with_label_and_guidance(tmp_path: Path) -> None:
    taxonomy = load_taxonomy(write(tmp_path, MINIMAL))

    prompt = taxonomy.prompt()

    assert "network: 통신·네트워크 — 5G·6G" in prompt
    assert "phone: 스마트폰" in prompt
    assert "반도체 자산 투자는 다루지 않는다." in prompt


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["axes"].pop("impact"),
        lambda d: d["axes"]["field"]["nodes"].append(
            {"key": "ai", "label": "중복", "description": "x"}
        ),
        lambda d: d["axes"]["field"]["nodes"].append(
            {"key": "Bad Key", "label": "x", "description": "x"}
        ),
        lambda d: d.update(revision=0),
        lambda d: d["axes"].update(region={"max_labels": 1, "nodes": []}),
        lambda d: d["rules"].update(max_fields=0),
        lambda d: d.pop("rules"),
        lambda d: d["axes"]["field"]["nodes"][0].update(color="red"),
    ],
)
def test_invalid_taxonomies_are_rejected(tmp_path: Path, mutate: object) -> None:
    data = yaml.safe_load(yaml.safe_dump(MINIMAL))
    mutate(data)  # type: ignore[operator]

    with pytest.raises(TaxonomyError):
        load_taxonomy(write(tmp_path, data))


def test_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(TaxonomyError):
        load_taxonomy(tmp_path / "nope.yaml")
