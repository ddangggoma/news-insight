"""LMArena: human-preference Elo ratings, read from its Hugging Face dataset (CC-BY-4.0)."""

import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from news_insight.benchmarks.sources import (
    HTTP_ERROR,
    SELECTOR_DRIFT,
    BenchmarkError,
    ScoreRow,
    SiteSnapshot,
    config_from_name,
    get_json,
    number,
)
from news_insight.net.mime import JSON_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "lmarena"
TITLE = "LMArena"
SOURCE_URL = "https://lmarena.ai/leaderboard"
LICENSE = "CC-BY-4.0 (Hugging Face 데이터셋 lmarena-ai/leaderboard-dataset)"
ATTRIBUTION = "LMArena"
DATASET = "lmarena-ai/leaderboard-dataset"
BOARDS = ("text_style_control", "webdev", "vision_style_control", "search_style_control", "agent")
PAGE = 100
MAX_PAGES = 50
# The datasets server builds the /filter index of a config on first use: requests time out or
# answer 500 "index is loading" for up to a few minutes, then the board is fast again. Retries
# share one budget per site run, so a server that stays down costs a worker ~4 minutes, not more.
RETRY_BUDGET_SECONDS = 240.0
RETRY_DELAY_SECONDS = 15.0
_clock = time.monotonic  # replaced in tests
_sleep = time.sleep
_FILTER = "https://datasets-server.huggingface.co/filter"
# Most boards rate models by Elo (rating, rating_lower, rating_upper); the agent board reports a
# task score with its own interval (score, score_ci_lower, score_ci_upper).
_VALUE_FIELDS = (
    ("rating", "rating_lower", "rating_upper"),
    ("score", "score_ci_lower", "score_ci_upper"),
)
_NOT_EXTRA = {"model_name", "organization", "category"}


def _page_url(board: str, offset: int) -> str:
    query = urlencode(
        {
            "dataset": DATASET,
            "config": board,
            "split": "latest",
            "where": "\"category\"='overall'",
            "offset": offset,
            "length": PAGE,
        }
    )
    return f"{_FILTER}?{query}"


def _page(fetcher: SafeFetcher, board: str, offset: int, deadline: float) -> list[dict[str, Any]]:
    url = _page_url(board, offset)
    while True:
        try:
            data = get_json(fetcher, url, JSON_MIME)
            break
        except BenchmarkError as exc:
            if not exc.retryable:
                raise
            if _clock() + RETRY_DELAY_SECONDS > deadline:
                raise BenchmarkError(
                    HTTP_ERROR,
                    f"{url}: still failing after the {RETRY_BUDGET_SECONDS:.0f} s retry budget",
                    status=exc.status,
                    retryable=True,
                ) from exc
            _sleep(RETRY_DELAY_SECONDS)
    entries = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise BenchmarkError(SELECTOR_DRIFT, f"{url}: no rows list")
    rows = [e["row"] for e in entries if isinstance(e, dict) and isinstance(e.get("row"), dict)]
    if len(rows) != len(entries):
        raise BenchmarkError(SELECTOR_DRIFT, f"{url}: rows without a row object")
    return rows


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    raw: dict[str, list[dict[str, Any]]] = {}
    scores: list[ScoreRow] = []
    published = ""
    deadline = _clock() + RETRY_BUDGET_SECONDS
    for board in BOARDS:
        rows: list[dict[str, Any]] = []
        for page in range(MAX_PAGES):
            batch = _page(fetcher, board, page * PAGE, deadline)
            rows.extend(batch)
            if len(batch) < PAGE:
                break
        if not rows:
            raise BenchmarkError(SELECTOR_DRIFT, f"lmarena {board}: no 'overall' rows")
        raw[board] = rows
        before = len(scores)
        for row in rows:
            score = _score(board, row)
            if score is not None:
                scores.append(score)
                date = row.get("leaderboard_publish_date")
                if isinstance(date, str) and date > published:
                    published = date
        if len(scores) == before:
            raise BenchmarkError(SELECTOR_DRIFT, f"lmarena {board}: no rating or score column")
    if not scores:
        raise BenchmarkError(SELECTOR_DRIFT, "lmarena: no usable rows")
    return SiteSnapshot(
        site=SITE,
        release=published or now.date().isoformat(),
        raw={"boards": raw},
        rows=scores,
    )


def _score(board: str, row: dict[str, Any]) -> ScoreRow | None:
    name = row.get("model_name")
    if not isinstance(name, str) or not name:
        return None
    for metric, low, high in _VALUE_FIELDS:
        value = number(row.get(metric))
        if value is None:
            continue
        org = row.get("organization")
        plotted = {metric, low, high}
        return ScoreRow(
            board=board,
            model_raw=name,
            org=org if isinstance(org, str) and org else None,
            config=config_from_name(name),
            metric=metric,
            value=value,
            ci_low=number(row.get(low)),
            ci_high=number(row.get(high)),
            # rank, votes or sessions, license, publish date, variance, cost per task...
            extra={
                k: v
                for k, v in row.items()
                if k not in _NOT_EXTRA | plotted and isinstance(v, int | float | str)
            },
        )
    return None
