"""Cross-track identifiers: arXiv ids, DOIs and GitHub repositories mentioned by an item."""

import re

ARXIV = re.compile(r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv:\s?)(\d{4}\.\d{4,5})", re.IGNORECASE)
DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>()\[\],;]+)", re.IGNORECASE)
GITHUB = re.compile(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100})")
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
    return refs
