"""Scale SEAL leaderboards (labs.scale.com/leaderboard): expert-built private evaluations.

The site is a Next.js app whose data rides in the page as flight chunks
(`self.__next_f.push([1,"…"])`). The index page lists every board with its top six rows; a
board's own page (`/leaderboard/<id>`) carries the full `entries`, or `variants` (each with its
`entries`) plus the `activeTab` the page opens on (SWE-Bench Pro: Full / HARD).

Read 2026-11-13. The site's default view: the index is a grid of cards, one per board, each
with its top entries; a board page is a table of Rank (UB), model and score ± its confidence
interval, in the served order. "Rank (UB)" is the site's own: 1 + the number of models whose
lower CI bound exceeds this model's upper bound, so ranks are shared. That rank is stored as
`extra.default_rank`; a row the site marks deprecated gets none (an assumption: no such row was
served on the day this was written).

A small set of boards is mirrored (BOARD_LIMIT): the ones named in PREFERRED when the index
lists them, then the index's first live "frontier" and "agentic" boards in page order. The list
is discovered from the index on every run, so a retired board drops out by itself.

Terms: robots.txt allows /leaderboard (only /api/, /studio, /draft/ are disallowed); the Scale
website terms (last updated 2021-08-25) name no licence for the data and do not mention
automated access, but grant use of the site "for your own internal purposes" and keep all
rights in its data with Scale.
"""

import json
import re
from datetime import datetime
from typing import Any

from news_insight.benchmarks.sources import (
    PARSE_ERROR,
    SELECTOR_DRIFT,
    BenchmarkError,
    ScoreRow,
    SiteSnapshot,
    get,
    number,
)
from news_insight.net.mime import HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "seal"
TITLE = "Scale SEAL"
SOURCE_URL = "https://labs.scale.com/leaderboard"
LICENSE = "라이선스 명시 없음 (Scale 웹사이트 약관: 내부 용도 열람, 데이터 권리는 Scale 보유)"
ATTRIBUTION = "SEAL Leaderboards (Scale AI)"
METRIC = "score"
MAX_BYTES = 8 * 1024 * 1024  # the index is 0.3 MB, a board page 0.1-0.2 MB
BOARD_LIMIT = 6
# always mirrored while the index lists them
PREFERRED = ("swe_bench_pro_public_v2", "hle-diamond", "mcp_atlas")
CATEGORIES = frozenset({"frontier", "agentic"})  # "safety" boards are left out
# the boards whose moves the spotlight hears about (public.benchmarks.SPOTLIGHT_BOARDS)
SPOTLIGHT = frozenset(
    {
        "hle-diamond",
        "mcp_atlas",
        "swe_bench_pro_public_v2:full",
        "swe_bench_pro_public_v2:hard",
    }
)

_PUSH = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.DOTALL)
_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_ENTRY_KEPT = (
    "model",
    "version",
    "rank",
    "score",
    "confidenceInterval_upper",
    "company",
    "isNew",
    "createdAt",
    "deprecated",
    "calibrationError",
    "contaminationMessage",
)


def _fail(message: str) -> BenchmarkError:
    return BenchmarkError(PARSE_ERROR, f"seal: {message}")


def flight(html: str) -> str:
    """The page's flight data: every `self.__next_f.push([1, "…"])` string, joined."""
    parts: list[str] = []
    for found in _PUSH.finditer(html):
        try:
            chunk = json.loads(found.group(1))
        except ValueError:
            continue
        if isinstance(chunk, list) and len(chunk) > 1 and isinstance(chunk[1], str):
            parts.append(chunk[1])
    return "".join(parts)


def _object(text: str, marker: str) -> Any:
    """The JSON object that starts at the first `marker` in the flight text, or None."""
    start = text.find(marker)
    if start < 0:
        return None
    try:
        found, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    return found


def categories(html: str) -> list[dict[str, Any]]:
    """The index page's boards, in page order."""
    data = _object(flight(html), '{"categories":')
    listed = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(listed, list):
        raise BenchmarkError(SELECTOR_DRIFT, "seal: the index page carries no categories")
    found = [c for c in listed if isinstance(c, dict) and isinstance(c.get("id"), str)]
    if not found:
        raise _fail("the index lists no boards")
    return found


def pick_boards(listed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The boards to mirror: one entry per id (its first card), in page order."""
    live: dict[str, dict[str, Any]] = {}
    for category in listed:
        board_id = category["id"]
        if category.get("deprecated") is True or not _ID.match(board_id):
            continue
        live.setdefault(board_id, category)
    preferred = [board_id for board_id in live if board_id in PREFERRED]
    others = [
        board_id
        for board_id, category in live.items()
        if board_id not in PREFERRED and category.get("category") in CATEGORIES
    ]
    chosen = set(preferred) | set(others[: max(0, BOARD_LIMIT - len(preferred))])
    return [category for board_id, category in live.items() if board_id in chosen]


def _entries(where: str, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise _fail(f"{where}: no entries")
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise _fail(f"{where}: entry {index} is not an object")
        if not isinstance(entry.get("model"), str) or not entry["model"].strip():
            raise _fail(f"{where}: entry {index} has no model")
        if number(entry.get("score")) is None or number(entry.get("rank")) is None:
            raise _fail(f"{where}: entry {index} has no score or rank")
    return [{k: entry[k] for k in _ENTRY_KEPT if k in entry} for entry in value]


def board_tables(board_id: str, html: str) -> list[dict[str, Any]]:
    """A board page's tables: one, or one per variant with the page's active tab first.
    Each: {"key", "variant", "label", "active", "entries"}."""
    text = flight(html)
    data = _object(text, '{"variants":')
    if isinstance(data, dict) and isinstance(data.get("variants"), list):
        active = data.get("activeTab")
        tables = []
        for variant in data["variants"]:
            if not isinstance(variant, dict) or not isinstance(variant.get("key"), str):
                raise _fail(f"{board_id}: a variant has no key")
            key = variant["key"]
            if not _ID.match(key):
                raise _fail(f"{board_id}: variant key {key!r}")
            label = variant.get("label")
            tables.append(
                {
                    "key": f"{board_id}:{key}",
                    "variant": key,
                    "label": label if isinstance(label, str) and label else None,
                    "active": key == active,
                    "entries": _entries(f"{board_id}:{key}", variant.get("entries")),
                }
            )
        if not tables:
            raise _fail(f"{board_id}: no variants")
        tables.sort(key=lambda table: not table["active"])  # stable: the open tab first
        return tables
    data = _object(text, '{"entries":')
    if not isinstance(data, dict):
        raise BenchmarkError(SELECTOR_DRIFT, f"seal: {board_id} page carries no entries")
    return [
        {
            "key": board_id,
            "variant": None,
            "label": None,
            "active": True,
            "entries": _entries(board_id, data.get("entries")),
        }
    ]


def _updated(entries: list[dict[str, Any]]) -> str:
    days = [e["createdAt"][:10] for e in entries if isinstance(e.get("createdAt"), str)]
    return max(days, default="")


def _rows(board: dict[str, Any], order: int) -> list[ScoreRow]:
    out = []
    for entry in board["entries"]:
        model = entry["model"].strip()
        score = float(entry["score"])
        half = number(entry.get("confidenceInterval_upper"))
        company = entry.get("company")
        company = company.strip() if isinstance(company, str) and company.strip() else None
        created = entry.get("createdAt")
        extra: dict[str, Any] = {
            "default_rank": None if entry.get("deprecated") is True else entry["rank"],
            "entry": model,
            "label": model,
            "board_title": board["title"],
            "board_order": order,
            "board_id": board["id"],
            "category": board["category"],
            "version": entry.get("version") or None,
            "is_new": entry.get("isNew") is True or None,
            "created": created[:10] if isinstance(created, str) else None,
            "ci_half": half,
            "calibration_error": number(entry.get("calibrationError")),
            "deprecated": entry.get("deprecated") is True or None,
        }
        out.append(
            ScoreRow(
                board=board["key"],
                model_raw=model[:200],
                org=company[:80] if company else None,
                config=None,
                metric=METRIC,
                value=score,
                ci_low=score - half if half is not None else None,
                ci_high=score + half if half is not None else None,
                extra={k: v for k, v in extra.items() if v is not None},
            )
        )
    return out


def _html(fetcher: SafeFetcher, url: str) -> str:
    return get(fetcher, url, HTML_MIME, max_bytes=MAX_BYTES).content.decode(
        "utf-8", errors="replace"
    )


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    chosen = pick_boards(categories(_html(fetcher, SOURCE_URL)))
    if not chosen:
        raise _fail("no live frontier or agentic board on the index")
    boards: dict[str, Any] = {}
    updated: dict[str, str] = {}
    scores: list[ScoreRow] = []
    for category in chosen:
        board_id = category["id"]
        name = category.get("name")
        for table in board_tables(board_id, _html(fetcher, f"{SOURCE_URL}/{board_id}")):
            title = table["label"] or (name.strip() if isinstance(name, str) else board_id)
            board = {
                "key": table["key"],
                "id": board_id,
                "variant": table["variant"],
                "title": title,
                "category": category.get("category") or None,
                "active": table["active"],
                "entries": table["entries"],
            }
            scores.extend(_rows(board, len(boards)))
            boards[table["key"]] = board
            updated[table["key"]] = _updated(table["entries"])
    return SiteSnapshot(
        site=SITE,
        release=max(updated.values(), default="") or now.date().isoformat(),
        raw={"boards": boards, "order": list(boards), "updated": updated},
        rows=scores,
    )
