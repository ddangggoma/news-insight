"""SimpleBench (simple-bench.com): trick questions of everyday reasoning that people without
special knowledge answer better than most models.

The page draws its table from one static script, `static/js/leaderboard-data.js`: a
`leaderboardData` array of `{ rank, model, score, organization, dateAdded }` object literals
(JavaScript, not JSON), followed by a three-row open-ended table and a price table that are not
read here.

Read 2026-11-13. The page opens on its "MCQ" tab (index.js renders `leaderboardData` on load):
the rows in file order with the columns Rank ("1st", and a NEW tag for two weeks after
`dateAdded`), Model, Score (AVG@5, "94.9%") and Organization. Two human reference rows
("Human Baseline*", "Highest Human Score*") sit among the models with rank "-". Each model's
rank number is `extra.default_rank`; the human rows have none (they are shown, never ranked)
and every row keeps its place in the file as `extra.position`.

Licence: none stated on the site ("명시 없음"); no robots.txt, no terms page.
"""

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
)
from news_insight.net.mime import JAVASCRIPT_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "simplebench"
TITLE = "SimpleBench"
SOURCE_URL = "https://simple-bench.com/"
LICENSE = "명시 없음"
ATTRIBUTION = "SimpleBench (simple-bench.com, AI Explained)"
DATA_URL = "https://simple-bench.com/static/js/leaderboard-data.js"
BOARD = "mcq"
METRIC = "score"

_STRING = r'"((?:[^"\\]|\\.)*)"'
_TABLE = re.compile(r"const\s+leaderboardData\s*=\s*\[(.*?)\n\];", re.DOTALL)
_ENTRY = re.compile(
    rf"\{{\s*rank:\s*{_STRING},\s*model:\s*{_STRING},\s*score:\s*{_STRING},"
    rf"\s*organization:\s*{_STRING},\s*dateAdded:\s*(?:{_STRING}|null)\s*\}}"
)
_RANK = re.compile(r"^(\d+)")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ESCAPE = re.compile(r"\\(.)")


def _fail(message: str) -> BenchmarkError:
    return BenchmarkError(PARSE_ERROR, f"simplebench: {message}")


def _text(literal: str) -> str:
    return _ESCAPE.sub(r"\1", literal).strip()


def entries(script: str) -> list[dict[str, Any]]:
    """The MCQ table's rows in file order: {rank, model, score, organization, date_added}."""
    table = _TABLE.search(script)
    if table is None:
        raise BenchmarkError(SELECTOR_DRIFT, "simplebench: leaderboardData not found")
    body = table.group(1)
    found = _ENTRY.findall(body)
    # every object literal of the table must be read: a new field or quoting style is loud
    if not found or len(found) != body.count("rank:"):
        raise _fail(f"read {len(found)} of {body.count('rank:')} entries")
    out = []
    for rank, model, score, organization, added in found:
        try:
            value = float(score.strip().rstrip("%"))
        except ValueError as exc:
            raise _fail(f"score {score!r} of {model!r} is not a number") from exc
        out.append(
            {
                "rank": rank.strip(),
                "model": _text(model),
                "score": value,
                "organization": _text(organization),
                "date_added": added if _DAY.match(added) else None,
            }
        )
    return out


def parse(script: str) -> tuple[dict[str, Any], list[ScoreRow]]:
    rows = entries(script)
    scores = []
    for position, row in enumerate(rows, start=1):
        number = _RANK.match(row["rank"])
        extra: dict[str, Any] = {
            "default_rank": int(number.group(1)) if number else None,
            "rank_label": row["rank"],
            "position": position,
            "entry": row["model"],
            "label": row["model"],
            "date_added": row["date_added"],
            "human": number is None or None,
        }
        scores.append(
            ScoreRow(
                board=BOARD,
                model_raw=row["model"][:200],
                org=row["organization"][:80] or None,
                config=None,
                metric=METRIC,
                value=row["score"],
                extra={k: v for k, v in extra.items() if v is not None},
            )
        )
    if not any("default_rank" in score.extra for score in scores):
        raise _fail("no ranked model")
    days = [row["date_added"] for row in rows if row["date_added"]]
    return {"entries": rows, "updated": {BOARD: max(days, default="")}}, scores


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    response = get(fetcher, DATA_URL, JAVASCRIPT_MIME)
    raw, scores = parse(response.content.decode("utf-8", errors="replace"))
    return SiteSnapshot(
        site=SITE,
        release=raw["updated"][BOARD] or now.date().isoformat(),
        raw=raw,
        rows=scores,
    )
