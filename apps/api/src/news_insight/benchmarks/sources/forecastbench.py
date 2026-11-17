"""ForecastBench (Forecasting Research Institute): how well models forecast questions whose
answers are not known yet, scored against superforecasters and the public.

forecastbench.org/leaderboards/ draws each tab from one generated script; the tournament tab's
is `assets/js/leaderboard_tournament_full.js`: a `const data = [...]` array of row objects
(written as a Python literal: single-quoted strings) and the DataTables setup that renders it,
including the line "last updated YYYY-MM-DD".

Read 2026-11-13. The page opens on the "Tournament" tab with anonymous teams hidden ("Show
anonymous teams" unticked), ordered by Overall, best first, 25 rows a page. Columns: Rank (the
file's own, counted over every row, so the first visible row can be rank 3; ties share a
rank), Team, Org, Model, Dataset (N), Dataset 95% CI, Market (N), Market 95% CI, Overall (N),
Overall 95% CI, "Supers > Forecaster?" and "Forecaster > Public?". Scores are Brier Index
percentages with one decimal (100 perfect, 50 always answering 50%). The rows that view shows
carry the file's rank as `extra.default_rank`; anonymous teams' rows are kept without one.

Licence: CC BY-SA 4.0 (the site's footer). robots.txt allows everything.
"""

import ast
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
from news_insight.net.mime import JAVASCRIPT_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "forecastbench"
TITLE = "ForecastBench"
SOURCE_URL = "https://www.forecastbench.org/leaderboards/"
LICENSE = "CC BY-SA 4.0"
ATTRIBUTION = "ForecastBench (Forecasting Research Institute), forecastbench.org"
DATA_URL = "https://www.forecastbench.org/assets/js/leaderboard_tournament_full.js"
BOARD = "tournament"
METRIC = "overall"
MAX_BYTES = 8 * 1024 * 1024  # 0.3 MB today
MAX_LITERAL = 4 * 1024 * 1024

_DATA = re.compile(r"const\s+data\s*=\s*(\[.*?\])\s*;\s*const\s", re.DOTALL)
_UPDATED = re.compile(r"last updated (\d{4}-\d{2}-\d{2})")
_INTERVAL = re.compile(r"^\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]$")
# the row's other cells, as the file names them → the key they are stored under
_TEXT = {
    "Team Name": "team",
    "Dataset 95% CI": "dataset_ci",
    "Market 95% CI": "market_ci",
    "Supers > Forecaster?": "supers_beat",
    "p-val Supers > Forecaster?": "supers_p",
    "Forecaster > Public?": "beats_public",
    "p-val Forecaster > Public?": "public_p",
}
_NUMBERS = {
    "Dataset": "dataset",
    "N dataset": "n_dataset",
    "Market": "market",
    "N market": "n_market",
    "N": "n",
}


def _fail(message: str) -> BenchmarkError:
    return BenchmarkError(PARSE_ERROR, f"forecastbench: {message}")


def rows_of(script: str) -> list[dict[str, Any]]:
    """The script's `data` array: JSON, else a Python literal (how the site writes it)."""
    found = _DATA.search(script)
    if found is None:
        raise BenchmarkError(SELECTOR_DRIFT, "forecastbench: the data array was not found")
    literal = found.group(1)
    if len(literal) > MAX_LITERAL:
        raise _fail(f"the data array is {len(literal)} characters")
    try:
        data = json.loads(literal)
    except ValueError:
        try:
            data = ast.literal_eval(literal)  # literals only: nothing is executed
        except (ValueError, SyntaxError, MemoryError, RecursionError) as exc:
            raise _fail("the data array is neither JSON nor a literal") from exc
    if not isinstance(data, list) or not data:
        raise _fail("the data array is empty")
    for index, row in enumerate(data):
        if not isinstance(row, dict):
            raise _fail(f"row {index} is not an object")
        if not isinstance(row.get("Model"), str) or not row["Model"].strip():
            raise _fail(f"row {index} has no Model")
        if number(row.get("Overall")) is None or number(row.get("Rank")) is None:
            raise _fail(f"row {index} has no Overall or Rank")
    return data


def anonymous(row: dict[str, Any]) -> bool:
    """The page's filter: a team whose name starts with "anonymous" is hidden by default."""
    team = row.get("Team Name")
    return isinstance(team, str) and team.lower().strip().startswith("anonymous")


def _interval(text: Any) -> tuple[float | None, float | None]:
    found = _INTERVAL.match(text.strip()) if isinstance(text, str) else None
    return (float(found.group(1)), float(found.group(2))) if found else (None, None)


def parse(script: str) -> tuple[dict[str, Any], list[ScoreRow]]:
    data = rows_of(script)
    scores = []
    for row in data:
        model = row["Model"].strip()
        hidden = anonymous(row)
        org = row.get("Model Organization")
        org = org.strip() if isinstance(org, str) and org.strip() else None
        team = row.get("Team Name")
        team = team.strip() if isinstance(team, str) and team.strip() else None
        low, high = _interval(row.get("Overall 95% CI"))
        extra: dict[str, Any] = {
            "default_rank": None if hidden else row["Rank"],
            "site_rank": row["Rank"],
            "entry": f"{team or ''}/{model}",
            "label": model,
            "anonymous": hidden or None,
        }
        for column, key in _NUMBERS.items():
            extra[key] = number(row.get(column))
        for column, key in _TEXT.items():
            value = row.get(column)
            extra[key] = value.strip()[:80] if isinstance(value, str) and value.strip() else None
        scores.append(
            ScoreRow(
                board=BOARD,
                model_raw=model[:200],
                org=org[:80] if org else None,
                config=None,
                metric=METRIC,
                value=float(row["Overall"]),
                ci_low=low,
                ci_high=high,
                extra={k: v for k, v in extra.items() if v is not None},
            )
        )
    if not any("default_rank" in score.extra for score in scores):
        raise _fail("every row is an anonymous team")
    updated = _UPDATED.search(script)
    raw = {"rows": data, "updated": {BOARD: updated.group(1) if updated else ""}}
    return raw, scores


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    response = get(fetcher, DATA_URL, JAVASCRIPT_MIME, max_bytes=MAX_BYTES)
    raw, scores = parse(response.content.decode("utf-8", errors="replace"))
    return SiteSnapshot(
        site=SITE,
        release=raw["updated"][BOARD] or now.date().isoformat(),
        raw=raw,
        rows=scores,
    )
