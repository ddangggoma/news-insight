from pathlib import Path

import pytest
import yaml

from news_insight.classify.keywords import (
    DEFAULT_ALIAS_PATH,
    AliasSeedError,
    clean_keyword,
    keyword_key,
    load_alias_seed,
)


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("  #온디바이스  AI ", "온디바이스 AI"),
        ("＃ＡＩ　칩", "AI 칩"),  # full-width forms (NFKC)
        ('"Galaxy S30"', "Galaxy S30"),
        ("##", None),
        ("   ", None),
    ],
)
def test_clean_keyword(raw: str, clean: str | None) -> None:
    assert clean_keyword(raw) == clean


def test_spacing_case_and_separator_variants_share_a_key() -> None:
    variants = ["온디바이스AI", "온디바이스 AI", "#온디바이스 ai", "온디바이스-AI", "온디바이스·AI"]

    assert {keyword_key(v) for v in variants} == {"온디바이스ai"}
    assert keyword_key("Wi-Fi 7") == keyword_key("WiFi7") == "wifi7"
    assert keyword_key("Node.js") == "node.js"
    assert keyword_key("#") is None


def test_shipped_alias_seed_maps_variants_to_canonical_names() -> None:
    seed = load_alias_seed(DEFAULT_ALIAS_PATH)

    assert seed.canonical("On-device AI") == "온디바이스 AI"
    assert seed.canonical("온디바이스AI") == "온디바이스 AI"
    assert seed.canonical("Samsung Electronics") == "삼성전자"
    assert seed.canonical("삼성전자") == "삼성전자"
    assert seed.canonical("unrelated") is None


def test_alias_seed_rejects_an_alias_claimed_twice(tmp_path: Path) -> None:
    path = tmp_path / "aliases.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "keywords": [
                    {"canonical": "애플", "aliases": ["Apple"]},
                    {"canonical": "애플 주식", "aliases": ["apple"]},
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    with pytest.raises(AliasSeedError):
        load_alias_seed(path)
