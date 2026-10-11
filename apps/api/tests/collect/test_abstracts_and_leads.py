"""Abstracts from research APIs and page leads when the description meta is empty (2026-10-11)."""

from datetime import UTC

from news_insight.collect.json_api import inverted_text, with_query
from news_insight.collect.page_meta import extract_meta
from news_insight.collect.presets import effective_config


def test_openalex_inverted_abstract_is_rebuilt_in_order() -> None:
    index = {"edge": [0], "AI": [1, 4], "runs": [2], "on": [3]}
    assert inverted_text(index) == "edge AI runs on AI"
    assert inverted_text(None) is None and inverted_text({}) is None


def test_query_overrides_replace_parameters_and_keep_the_rest() -> None:
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=x&format=json&resultType=lite"
    out = with_query(url, {"resultType": "core"})
    assert "resultType=core" in out and "resultType=lite" not in out and "format=json" in out
    assert with_query(url, {}) == url


def test_research_presets_map_abstracts() -> None:
    assert effective_config({"preset": "crossref_works"})["fields"]["summary"] == "abstract"
    openalex = effective_config({"preset": "openalex_works"})["fields"]
    assert openalex["summary_index"] == "abstract_inverted_index"
    europepmc = effective_config({"preset": "europepmc_search"})
    assert europepmc["fields"]["summary"] == "abstractText"
    assert europepmc["query_overrides"] == {"resultType": "core"}


def test_page_lead_fills_an_empty_description() -> None:
    html = """<html><head><meta name="description" content="  ">
    <meta property="article:published_time" content="2026-10-09T10:00:00Z"></head>
    <body><nav><p>Home · Products · About us and everything else we link to here</p></nav>
    <article><h1>Status report</h1><p>short</p>
    <p>The cluster administration team replaced the package builders and moved mirrors to new
    hardware this quarter, cutting build times in half.</p>
    <p>Accept all cookies to continue reading this page and our newsletter.</p></article>
    <footer><p>Copyright notice long enough to count as a paragraph of text here.</p></footer>
    </body></html>"""
    meta = extract_meta(html, assume_tz=UTC)
    assert meta.description is not None
    assert meta.description.startswith("The cluster administration team")
    assert "cookies" not in meta.description and "Copyright" not in meta.description
    assert meta.published_at is not None  # the date is read before navigation is stripped
