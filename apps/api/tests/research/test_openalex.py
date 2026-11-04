"""OpenAlex single-work answers (real responses, trimmed) → research metadata."""

import json
from pathlib import Path
from typing import Any

import pytest

from news_insight.research.openalex import doi_for_ref, parse_work, work_url

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"openalex_{name}.json").read_text())
    return data


def test_parse_company_paper_on_arxiv() -> None:
    work = parse_work(load("attention"))

    assert work.openalex_id == "W2626778328"
    assert work.doi == "10.48550/arxiv.1706.03762"
    assert work.venue == "arXiv (Cornell University)"
    assert work.oa_field == "Computer Science"
    assert work.oa_subfield == "Artificial Intelligence"
    assert work.oa_topic == "Natural Language Processing Techniques"
    names = [(i.name, i.type, i.country) for i in work.institutions]
    assert names == [
        ("Google (United States)", "company", "US"),
        ("University of Southern California", "education", "US"),
        ("University of Toronto", "education", "CA"),
    ]
    assert work.institutions[0].ror == "https://ror.org/00njsd438"
    assert work.countries == ["CA", "US"]
    assert work.cited_by > 1000
    assert work.counts_by_year[0] == {"year": 2026, "cited_by_count": 7145}


def test_parse_journal_paper_with_fwci() -> None:
    work = parse_work(load("alphafold"))

    assert work.venue == "Nature"
    assert work.oa_subfield == "Molecular Biology"
    assert work.fwci == pytest.approx(2020.1166)
    assert {i.name for i in work.institutions} == {
        "Google DeepMind (United Kingdom)",
        "Seoul National University",
    }
    assert work.countries == ["GB", "KR"]


def test_recent_arxiv_paper_without_citations() -> None:
    work = parse_work(load("arxiv_recent"))

    assert work.cited_by == 0 and work.fwci is None and work.counts_by_year == []
    assert work.countries == ["PL", "SG"]
    assert {i.type for i in work.institutions} == {"education", "facility"}


def test_parse_tolerates_missing_blocks() -> None:
    work = parse_work({"id": "https://openalex.org/W1", "authorships": [{"institutions": None}]})

    assert work.openalex_id == "W1"
    assert work.doi is None and work.venue is None and work.oa_field is None
    assert work.institutions == [] and work.countries == []
    assert work.cited_by == 0


def test_long_names_are_cut_to_the_column() -> None:
    long = "x" * 500
    work = parse_work(
        {
            "id": "https://openalex.org/W2",
            "primary_location": {"source": {"display_name": long}},
            "authorships": [{"institutions": [{"display_name": long, "type": "company"}]}],
        }
    )

    assert work.venue is not None and len(work.venue) == 300
    assert len(work.institutions[0].name) == 200


def test_arxiv_ids_are_looked_up_by_their_datacite_doi() -> None:
    assert doi_for_ref("arxiv", "2610.38252") == "10.48550/arxiv.2610.38252"
    assert doi_for_ref("doi", "10.1038/S41586-021-03819-2") == "10.1038/s41586-021-03819-2"
    assert doi_for_ref("github", "a/b") is None


def test_work_url_quotes_the_doi_but_keeps_its_slash() -> None:
    url = work_url("10.1002/(sici)1097-4636#x")

    assert url.startswith("https://api.openalex.org/works/doi:10.1002/")
    assert "#" not in url and "select=" in url
