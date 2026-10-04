from news_insight.stories.refs import extract_refs


def test_extracts_arxiv_doi_and_github_refs() -> None:
    refs = extract_refs(
        "https://arxiv.org/abs/2610.01985v1",
        "Code: https://github.com/ggml-org/llama.cpp and doi 10.1038/s41586-026-01234-5.",
        "arXiv:2609.12345 · https://doi.org/10.48550/arXiv.2608.00001 · github.com/orgs/x",
    )

    assert refs == {
        ("arxiv", "2610.01985"),
        ("arxiv", "2609.12345"),
        ("arxiv", "2608.00001"),
        ("github", "ggml-org/llama.cpp"),
        ("doi", "10.1038/s41586-026-01234-5"),
    }
