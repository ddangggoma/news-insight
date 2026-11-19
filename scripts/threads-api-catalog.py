#!/usr/bin/env python3
"""Turn the Threads crawler sources into official Threads API sources.

Switch-over steps: docs/runbooks/threads-api.md, section 4.

Run from apps/api, so PyYAML and the catalog schema are importable:

    cd apps/api
    uv run python ../../scripts/threads-api-catalog.py                 # print the API entries
    uv run python ../../scripts/threads-api-catalog.py --write         # add them to the catalog
    uv run python ../../scripts/threads-api-catalog.py --drop-crawler  # remove converted crawler
                                                                       # entries, print their keys

`--kind search` (default) converts the 100 `threads-search-*` keyword searches; `--kind profile`
or `--kind all` also converts `threads-profile-*` (profile_posts needs advanced access to
threads_profile_discovery, except for @meta, @threads, @instagram and @facebook).

A converted source keeps its keyword, cadence (`min_interval_minutes`), themes and freshness
window, gets a new key (`threads-search-x` -> `threads-api-search-x`) so crawler and API
history stay apart, and reads its token from SOURCE_SECRET_THREADS_TOKEN as a Bearer header.
The catalog file is edited as text, so every other entry keeps its formatting.
"""

import argparse
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import yaml

CATALOG = Path(__file__).resolve().parents[1] / "apps" / "api" / "catalog" / "sources.yaml"
GRAPH = "https://graph.threads.net/v1.0"
ENTRY_START = "  - key: "
CRAWLER_ONLY = {"mode", "manual_review", "crawl_permitted", "robots_checked", "robots_note"}
PREFIXES = {"search": "threads-search-", "profile": "threads-profile-"}


def api_key(key: str) -> str:
    return "threads-api-" + key.removeprefix("threads-")


def api_entry(entry: dict[str, Any], *, search_type: str = "TOP") -> dict[str, Any]:
    """The official-API twin of one crawler entry."""
    parts = urlsplit(str(entry["endpoint_url"]))
    if entry["key"].startswith(PREFIXES["search"]):
        [keyword] = parse_qs(parts.query)["q"]
        query = urlencode({"q": keyword, "search_type": search_type}, quote_via=quote)
        endpoint, preset = f"{GRAPH}/keyword_search?{query}", "threads_keyword_search"
    else:
        username = parts.path.strip("/").removeprefix("@")
        if not username or "/" in username:
            raise ValueError(f"{entry['key']}: no profile name in {entry['endpoint_url']}")
        endpoint = f"{GRAPH}/profile_posts?{urlencode({'username': username})}"
        preset = "threads_profile_posts"
    config = {
        "preset": preset,
        "auth": {"secret": "THREADS_TOKEN"},
        **{k: v for k, v in (entry.get("config") or {}).items() if k not in CRAWLER_ONLY},
    }
    converted: dict[str, Any] = {
        "key": api_key(entry["key"]),
        "name": str(entry["name"]).replace("Threads", "Threads API", 1),
        "track": entry["track"],
        "category": entry["category"],
        "access_method": "json_api",
        "endpoint_url": endpoint,
        "official_domain": entry["official_domain"],
        "operator": "Meta Platforms (Threads API)",
        "region": entry["region"],
        "language": entry["language"],
        "poll_class": entry["poll_class"],
        # the API documents no reaction counts on other users' posts
        "dx_relevance": str(entry["dx_relevance"])
        .replace("화제·반응 신호", "화제 신호")
        .replace("새 글과 반응", "새 글"),
        "terms_url": "https://developers.facebook.com/terms/",
        "storage_right": entry.get("storage_right", "excerpt_allowed"),
        "config": config,
    }
    return converted


class _NoAliases(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def entry_text(entry: dict[str, Any]) -> str:
    """One catalog entry in the file's own layout (two-space list under `sources:`)."""
    dumped = yaml.dump(
        [entry],
        Dumper=_NoAliases,
        sort_keys=False,
        allow_unicode=True,
        width=1000,
        default_flow_style=False,
    )
    return "".join(f"  {line}" if line.strip() else line for line in dumped.splitlines(True))


def blocks(text: str) -> tuple[str, list[tuple[str, str]]]:
    """The head before the first entry and each (key, entry text), in file order."""
    lines = text.splitlines(True)
    starts = [i for i, line in enumerate(lines) if line.startswith(ENTRY_START)]
    if not starts:
        return text, []
    head = "".join(lines[: starts[0]])
    found = []
    for start, end in zip(starts, starts[1:] + [len(lines)], strict=True):
        key = lines[start][len(ENTRY_START) :].strip()
        found.append((key, "".join(lines[start:end])))
    return head, found


def crawler_entries(catalog: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    prefixes = tuple(PREFIXES.values()) if kind == "all" else (PREFIXES[kind],)
    return [
        entry
        for entry in catalog["sources"]
        if entry["key"].startswith(prefixes) and entry.get("access_method") == "crawler"
    ]


def validate(text: str) -> None:
    """Reject a catalog the API would refuse to load (schema, presets, unique keys)."""
    try:
        from news_insight.sources.catalog import Catalog
    except ImportError:
        print("warning: run from apps/api with uv to validate the catalog schema", file=sys.stderr)
        return
    Catalog.model_validate(yaml.safe_load(text))


def with_api_entries(text: str, kind: str, search_type: str) -> tuple[str, list[str]]:
    catalog = yaml.safe_load(text)
    present = {entry["key"] for entry in catalog["sources"]}
    added = [
        api_entry(entry, search_type=search_type)
        for entry in crawler_entries(catalog, kind)
        if api_key(entry["key"]) not in present
    ]
    if not added:
        return text, []
    body = text if text.endswith("\n") else text + "\n"
    return body + "".join(entry_text(entry) for entry in added), [e["key"] for e in added]


def without_crawler_entries(text: str, kind: str) -> tuple[str, list[str]]:
    """Drop crawler entries whose API twin is in the catalog; others stay."""
    catalog = yaml.safe_load(text)
    present = {entry["key"] for entry in catalog["sources"]}
    drop = {
        entry["key"] for entry in crawler_entries(catalog, kind) if api_key(entry["key"]) in present
    }
    head, found = blocks(text)
    kept = "".join(block for key, block in found if key not in drop)
    return head + kept, sorted(drop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--kind", choices=("search", "profile", "all"), default="search")
    parser.add_argument("--search-type", choices=("TOP", "RECENT"), default="TOP")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--write", action="store_true", help="add the API entries to the catalog")
    action.add_argument(
        "--drop-crawler",
        action="store_true",
        help="remove converted crawler entries from the catalog and print their keys",
    )
    args = parser.parse_args(argv)
    text = args.catalog.read_text(encoding="utf-8")

    if args.drop_crawler:
        updated, keys = without_crawler_entries(text, args.kind)
    else:
        updated, keys = with_api_entries(text, args.kind, args.search_type)
        if not args.write:
            catalog = yaml.safe_load(updated)
            new = [entry for entry in catalog["sources"] if entry["key"] in set(keys)]
            sys.stdout.write("".join(entry_text(entry) for entry in new))
            print(f"# {len(keys)} API entries (not written; add --write)", file=sys.stderr)
            return 0
    validate(updated)
    if updated != text:
        args.catalog.write_text(updated, encoding="utf-8")
    if args.drop_crawler:
        sys.stdout.write("".join(f"{key}\n" for key in keys))
    print(
        f"# {'removed' if args.drop_crawler else 'added'} {len(keys)} entries in {args.catalog}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
