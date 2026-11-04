"""CPC/IPC codes: parsing the stored forms and mapping them to the 12 technology fields."""

import pytest

from news_insight.patents.classification import (
    codes_from_query,
    codes_from_summary,
    fields_for,
    load_cpc_fields,
    parse_code,
    parse_publication,
)
from news_insight.taxonomy.catalog import FIELD_KEYS


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("G06N 3/08", "G06N 3/08"),
        ("G06N3/08", "G06N 3/08"),
        ("g06n   3 / 084", "G06N 3/084"),
        ("H04W0072040000", "H04W 72/04"),  # OPS cpci without separators
        ("H01M", "H01M"),  # subclass alone (an OPS query)
        ("Y02E 60/10", "Y02E 60/10"),
        ("not a code", None),
        ("Z99Z 1/00", None),
    ],
)
def test_parse_code(raw: str, code: str | None) -> None:
    assert parse_code(raw) == code


def test_codes_from_the_eps_pilot_summary() -> None:
    summary = "EP4815724NWA1; IPC: A01K 1/02, B60P 3/04, B60R 22/18, A01K 1/02"

    assert codes_from_summary(summary) == ([], ["A01K 1/02", "B60P 3/04", "B60R 22/18"])


def test_codes_from_a_summary_with_cpc_and_ipc() -> None:
    summary = "Abstract text. CPC: G06N 3/08, G06V 10/82; IPC: G06N 3/04"

    assert codes_from_summary(summary) == (["G06N 3/08", "G06V 10/82"], ["G06N 3/04"])
    assert codes_from_summary("An abstract that mentions no codes.") == ([], [])
    assert codes_from_summary(None) == ([], [])


def test_codes_from_an_ops_query() -> None:
    assert codes_from_query("pn=US and cpc=G06N and pd>={today-30d}") == ["G06N"]
    assert codes_from_query("pn=CN and (cpc=H01M or cpc = H10K50/11)") == ["H01M", "H10K 50/11"]
    assert codes_from_query(None) == []


@pytest.mark.parametrize(
    ("stable_id", "parsed"),
    [
        ("epo:EP4815726NWA1", ("EP4815726", "A1", "EP")),
        ("US2025123456A1", ("US2025123456", "A1", "US")),
        ("CN118123456A", ("CN118123456", "A", "CN")),
        ("US12264976", ("US12264976", None, "US")),
        ("WO2025/123456", ("WO2025123456", None, "WO")),
        ("https://example.com/x", (None, None, None)),
    ],
)
def test_parse_publication(
    stable_id: str, parsed: tuple[str | None, str | None, str | None]
) -> None:
    assert parse_publication(stable_id) == parsed


def test_map_covers_the_design_examples() -> None:
    expected = {
        "G06N 3/08": "ai",
        "G06V 10/82": "ai",
        "H04W 72/04": "connectivity",
        "H01M 10/052": "energy",
        "H10K 59/12": "display_av",
        "G09G 3/32": "display_av",
        "B25J 9/16": "robotics_mobility",
        "H01L 23/538": "semis",
        "H10B 12/00": "semis",
        "B60W 30/09": "robotics_mobility",
        "G16H 50/20": "health_tech",
        "H04L 9/32": "security",
        "H04L 5/00": "connectivity",
        "G06N 10/40": "frontier",  # quantum computing inside the AI subclass
    }
    for code, field in expected.items():
        assert fields_for([code]) == [field], code


def test_every_field_has_classifications_and_every_target_is_a_field() -> None:
    mapping = load_cpc_fields()
    targets = set(mapping.subclasses.values()) | set(mapping.groups.values())

    assert targets <= FIELD_KEYS
    assert targets == FIELD_KEYS


def test_fields_keep_the_main_classification_first_and_skip_unknown_codes() -> None:
    assert fields_for(["A01K 1/02", "H01M 10/44", "G06N 3/08", "H01M 4/13"]) == ["energy", "ai"]
    assert fields_for(["A01K 1/02"]) == []
    assert fields_for(["H01M"]) == ["energy"]
