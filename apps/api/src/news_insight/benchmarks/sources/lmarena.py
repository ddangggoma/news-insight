"""LMArena: human-preference Elo ratings, read from its Hugging Face dataset (CC-BY-4.0).

Each board's `latest` split is one small parquet file in the dataset repo (the Hub answers 302
to a CDN host); the datasets-server /filter API that used to serve the same rows fails on a
share of its pages, so it is not used.
"""

import io
import math
import time
from datetime import date, datetime
from typing import Any

import pyarrow.parquet as pq
from pyarrow import ArrowException

from news_insight.benchmarks.sources import (
    SELECTOR_DRIFT,
    BenchmarkError,
    ScoreRow,
    SiteSnapshot,
    config_from_name,
    get,
    number,
)
from news_insight.net.safe_fetch import SafeFetcher

SITE = "lmarena"
TITLE = "LMArena"
SOURCE_URL = "https://lmarena.ai/leaderboard"
LICENSE = "CC-BY-4.0 (Hugging Face 데이터셋 lmarena-ai/leaderboard-dataset)"
ATTRIBUTION = "LMArena"
DATASET = "lmarena-ai/leaderboard-dataset"
BOARDS = ("text_style_control", "webdev", "vision_style_control", "search_style_control", "agent")
MAX_BYTES = 20 * 1024 * 1024  # a board is ~0.6 MB at most today
PARQUET_MIME = frozenset({"application/octet-stream", "application/vnd.apache.parquet"})
RETRY_DELAY_SECONDS = 5.0  # one retry of a transient HTTP error (the CDN or the Hub hiccups)
_sleep = time.sleep  # replaced in tests
# Most boards rate models by Elo (rating, rating_lower, rating_upper); the agent board reports a
# task score with its own interval (score, score_ci_lower, score_ci_upper).
_VALUE_FIELDS = (
    ("rating", "rating_lower", "rating_upper"),
    ("score", "score_ci_lower", "score_ci_upper"),
)
_NOT_EXTRA = {"model_name", "organization", "category"}
OVERALL = "overall"


def parquet_url(board: str) -> str:
    return f"https://huggingface.co/datasets/{DATASET}/resolve/main/{board}/latest-00000-of-00001.parquet"


def _download(fetcher: SafeFetcher, url: str) -> bytes:
    try:
        return get(fetcher, url, PARQUET_MIME, max_bytes=MAX_BYTES).content
    except BenchmarkError as exc:
        if not exc.retryable:
            raise
    _sleep(RETRY_DELAY_SECONDS)
    return get(fetcher, url, PARQUET_MIME, max_bytes=MAX_BYTES).content


def _overall_rows(fetcher: SafeFetcher, board: str) -> list[dict[str, Any]]:
    url = parquet_url(board)
    content = _download(fetcher, url)
    try:
        table = pq.read_table(io.BytesIO(content))
        if "category" not in table.column_names:
            raise BenchmarkError(SELECTOR_DRIFT, f"{url}: no category column")
        rows: list[dict[str, Any]] = table.to_pylist()
    except (ArrowException, OSError) as exc:
        raise BenchmarkError(SELECTOR_DRIFT, f"{url}: not a parquet file ({exc})") from exc
    return [_finite(row) for row in rows if row.get("category") == OVERALL]


def _finite(row: dict[str, Any]) -> dict[str, Any]:
    """The row with NaN and infinity as null: the snapshot's JSON cannot hold them."""
    return {k: None if isinstance(v, float) and not math.isfinite(v) else v for k, v in row.items()}


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    raw: dict[str, list[dict[str, Any]]] = {}
    scores: list[ScoreRow] = []
    published = ""
    for board in BOARDS:
        rows = _overall_rows(fetcher, board)
        if not rows:
            raise BenchmarkError(SELECTOR_DRIFT, f"lmarena {board}: no 'overall' rows")
        raw[board] = rows
        before = len(scores)
        for row in rows:
            score = _score(board, row)
            if score is not None:
                scores.append(score)
                day = _day(row.get("leaderboard_publish_date"))
                if day > published:
                    published = day
        if len(scores) == before:
            raise BenchmarkError(SELECTOR_DRIFT, f"lmarena {board}: no rating or score column")
    return SiteSnapshot(
        site=SITE,
        release=published or now.date().isoformat(),
        raw={"boards": raw},
        rows=scores,
    )


def _day(value: Any) -> str:
    """The publish date as YYYY-MM-DD, whether the file stores a string or a date."""
    if isinstance(value, date):  # datetime is a date
        return value.isoformat()[:10]
    return value if isinstance(value, str) else ""


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
