"""Cross-track identifiers mentioned by an item: arXiv ids, DOIs, GitHub repositories, and
(checklist SIG-1) CVE ids, 3GPP specifications, patent publication numbers and Hugging Face
models — so a vulnerability or a standard can be followed from advisory to forum to news."""

import re

ARXIV = re.compile(r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv:\s?)(\d{4}\.\d{4,5})", re.IGNORECASE)
DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>()\[\],;]+)", re.IGNORECASE)
GITHUB = re.compile(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100})")
CVE = re.compile(r"\bCVE-(\d{4})-(\d{4,7})\b", re.IGNORECASE)
# 3GPP technical specifications and reports: "TS 38.300", "3GPP TR 22.837", "TS38.331"
THREEGPP = re.compile(r"\b(?:3GPP\s+)?(TS|TR)\s?(\d{2}\.\d{3})\b")
# patent publications: US 2025/0123456 A1, US11,234,567 B2, EP 4123456 A1, WO 2025/123456,
# KR 10-2025-0012345
PATENT = re.compile(
    r"\b(US\s?\d{4}/\d{7}|US\s?\d{1,2},?\d{3},?\d{3}|EP\s?\d{7}|WO\s?\d{4}/\d{6}"
    r"|KR\s?10-\d{4}-\d{7})(?:\s?[ABUY]\d)?\b"
)
HUGGINGFACE = re.compile(r"huggingface\.co/([A-Za-z0-9][\w.-]{0,95}/[A-Za-z0-9][\w.-]{0,95})")
HUGGINGFACE_RESERVED = frozenset(
    {
        "datasets",
        "spaces",
        "docs",
        "blog",
        "papers",
        "models",
        "collections",
        "learn",
        "join",
        "login",
    }
)
GITHUB_RESERVED = frozenset(
    {
        "orgs",
        "settings",
        "features",
        "topics",
        "collections",
        "trending",
        "marketplace",
        "sponsors",
        "login",
        "about",
        "pricing",
        "security",
        "advisories",
        "apps",
        "search",
        "site",
    }
)


def extract_refs(*texts: str | None) -> set[tuple[str, str]]:
    blob = " ".join(text for text in texts if text)
    refs: set[tuple[str, str]] = set()
    for match in ARXIV.finditer(blob):
        refs.add(("arxiv", match.group(1)))
    for match in DOI.finditer(blob):
        doi = match.group(1).rstrip(".").lower()
        if doi.startswith("10.48550/arxiv."):
            refs.add(("arxiv", doi.removeprefix("10.48550/arxiv.")))
        else:
            refs.add(("doi", doi))
    for match in GITHUB.finditer(blob):
        owner, repo = match.group(1).split("/", 1)
        repo = repo.removesuffix(".git").rstrip(".")
        if owner.lower() not in GITHUB_RESERVED and repo:
            refs.add(("github", f"{owner}/{repo}".lower()))
    for match in CVE.finditer(blob):
        refs.add(("cve", f"CVE-{match.group(1)}-{match.group(2)}"))
    for match in THREEGPP.finditer(blob):
        refs.add(("3gpp", f"{match.group(1).upper()} {match.group(2)}"))
    for match in PATENT.finditer(blob):
        refs.add(("patent", re.sub(r"[\s,]", "", match.group(1)).upper()))
    for match in HUGGINGFACE.finditer(blob):
        owner, name = match.group(1).split("/", 1)
        if owner.lower() not in HUGGINGFACE_RESERVED:
            refs.add(("hf", f"{owner}/{name.rstrip('.')}".lower()))
    return refs
