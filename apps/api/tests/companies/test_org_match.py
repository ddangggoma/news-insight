"""Organisation names from OpenAlex institutions and patent applicants → registry keys."""

import pytest

from news_insight.companies.catalog import seed_alias_map
from news_insight.companies.service import match_company, org_spellings


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Google (United States)", "google"),  # OpenAlex appends the country
        ("Google DeepMind (United Kingdom)", "googledeepmind"),
        ("Samsung (South Korea)", "samsungelectronics"),  # alias "samsung"
        ("SAMSUNG ELECTRONICS CO LTD", "samsungelectronics"),  # EPO epodoc applicant
        ("Samsung Electronics Co., Ltd.", "samsungelectronics"),  # EPO original applicant
        ("LG Display Co., Ltd.", "lgdisplay"),
        ("Microsoft Technology Licensing, LLC", None),  # not a registered spelling
        ("NVIDIA Corporation", "nvidia"),
        ("Apple Inc.", "apple"),
        ("Seoul National University", None),
        ("", None),
    ],
)
def test_match_company_strips_country_and_legal_suffixes(name: str, key: str | None) -> None:
    assert match_company(name, seed_alias_map()) == key


def test_spellings_try_the_name_as_written_first() -> None:
    spellings = org_spellings("Meta (Israel)")

    assert spellings[0] == "meta(israel)"
    assert "meta" in spellings


def test_a_suffix_alone_is_not_a_name() -> None:
    assert org_spellings("Inc.") == ["inc."]
    assert match_company("Co., Ltd.", {"co": "x", "ltd": "y"}) is None
