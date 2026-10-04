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


def test_security_standard_patent_and_model_identifiers() -> None:
    refs = extract_refs(
        "Patch for cve-2026-12345 and CVE-2025-0001 released",
        "3GPP TS 38.300 and TR22.837 updates; also 'TS 1.2' is not a spec",
        "Granted US 11,234,567 B2 and published US 2025/0123456 A1, EP 4123456 A1, "
        "KR 10-2025-0012345",
        "Weights at https://huggingface.co/Qwen/Qwen3-8B. and huggingface.co/datasets/x/y",
    )

    assert {r for r in refs if r[0] == "cve"} == {
        ("cve", "CVE-2026-12345"),
        ("cve", "CVE-2025-0001"),
    }
    assert {r for r in refs if r[0] == "3gpp"} == {("3gpp", "TS 38.300"), ("3gpp", "TR 22.837")}
    assert {r for r in refs if r[0] == "patent"} == {
        ("patent", "US11234567"),
        ("patent", "US2025/0123456"),
        ("patent", "EP4123456"),
        ("patent", "KR10-2025-0012345"),
    }
    assert {r for r in refs if r[0] == "hf"} == {("hf", "qwen/qwen3-8b")}
