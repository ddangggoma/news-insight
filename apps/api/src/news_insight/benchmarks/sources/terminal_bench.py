"""Terminal-Bench (tbench.ai): terminal tasks solved by an agent harness + model + effort.

The site reads its boards from a Supabase edge function (`leaderboard-read`, anonymous); the
same JSON is what www.tbench.ai renders. Three boards are kept: 4.0 (the one the site opens on),
3.0 and 2.1. Each board must keep the shape we read (its columns, its rank order, each row's
agent, model, effort and accuracy): anything else is a `parse_error`, and the last good snapshot
stays (the endpoint is undocumented, so a change has to be loud).

The site's table opens with "best effort" on (its `efforts=best` default): one row per model and
agent, the effort with the highest accuracy (the first one served on a tie), ranked again over
those rows the way the site counts (equal accuracy, equal rank). That default view is computed
here and stored on each row: `extra.default_rank` on the rows the table shows, nothing on the
rest. Its columns: rank, model (effort in brackets), agent, resolution rate with the 95% interval
as whiskers, release date, tokens and cost. Read from the page script 2026-11-08.
"""

import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from news_insight.benchmarks.sources import (
    PARSE_ERROR,
    BenchmarkError,
    ScoreRow,
    SiteSnapshot,
    get_json,
    number,
)
from news_insight.net.mime import JSON_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "terminal_bench"
TITLE = "Terminal-Bench"
SOURCE_URL = "https://www.tbench.ai/"
LICENSE = "Apache-2.0 (harbor-framework/terminal-bench 저장소), 사이트 이용약관 없음"
ATTRIBUTION = "Terminal-Bench (Stanford · Laude Institute · Harbor)"
API_URL = "https://ofhuhcpkvzjlejydnvyd.supabase.co/functions/v1/leaderboard-read"
METRIC = "accuracy"
# (board, package, leaderboard name): the site's HOME_BENCHMARKS, newest first
BOARDS = (
    ("4.0", "terminal-bench/terminal-bench", "4-0-0"),
    ("3.0", "terminal-bench/terminal-bench", "3-0-0"),
    ("2.1", "terminal-bench/terminal-bench-2-1", "main"),
)
DEFAULT_BOARD = "4.0"
RETRY_DELAY_SECONDS = 5.0  # the function answers a transient server_error now and then
_sleep = time.sleep  # replaced in tests
# what the table and the summary use beyond accuracy, as the board serves them
_METRICS_KEPT = (
    "n_trials",
    "successes",
    "pass_at_2",
    "pass_at_3",
    "pass_at_4",
    "pass_at_5",
    "total_tokens",
    "output_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "total_cost_usd",
    "avg_trial_duration_sec",
    "accuracy_stderr",
)
_DISPLAY_KEPT = ("display_accuracy", "display_cost", "display_total_tokens")
_LEADERBOARD_KEPT = ("name", "title", "columns", "rank_by", "updated_at")


def board_url(package: str, name: str) -> str:
    return f"{API_URL}?{urlencode({'package': package, 'name': name})}"


def _download(fetcher: SafeFetcher, url: str) -> Any:
    try:
        return get_json(fetcher, url, JSON_MIME)
    except BenchmarkError as exc:
        if not (exc.retryable or (exc.status or 0) >= 500):
            raise
    _sleep(RETRY_DELAY_SECONDS)
    return get_json(fetcher, url, JSON_MIME)


def _fail(board: str, message: str) -> BenchmarkError:
    return BenchmarkError(PARSE_ERROR, f"terminal-bench {board}: {message}")


def _label(value: Any) -> str | None:
    """A {url, label} link's label (the site's parseLeaderboardLink)."""
    if isinstance(value, dict):
        label = value.get("label")
        return label.strip() if isinstance(label, str) and label.strip() else None
    return None


def _url(value: Any) -> str | None:
    url = value.get("url") if isinstance(value, dict) else None
    return url if isinstance(url, str) and url else None


def validate(board: str, data: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The board's leaderboard and rows, or a parse_error naming what moved."""
    if not isinstance(data, dict):
        raise _fail(board, "not an object")
    if "error" in data and "rows" not in data:
        raise _fail(board, f"error answer {data.get('error')!r}")
    leaderboard, rows = data.get("leaderboard"), data.get("rows")
    if not isinstance(leaderboard, dict) or not isinstance(rows, list):
        raise _fail(board, "no leaderboard object or rows list")
    if not isinstance(leaderboard.get("updated_at"), str):
        raise _fail(board, "no updated_at")
    rank_by = leaderboard.get("rank_by")
    if rank_by != [{"accessor": "metrics.accuracy", "direction": "desc"}]:
        raise _fail(board, f"rank_by changed to {rank_by!r}")
    columns = leaderboard.get("columns")
    accessors = (
        {c.get("accessor") for c in columns if isinstance(c, dict)}
        if isinstance(columns, list)
        else set()
    )
    for needed in ("metadata.agent_display", "metadata.model_display", "metrics.accuracy"):
        if needed not in accessors:
            raise _fail(board, f"column {needed} missing")
    if not rows:
        raise _fail(board, "no rows")
    for index, row in enumerate(rows):
        where = f"row {index}"
        if not isinstance(row, dict):
            raise _fail(board, f"{where} is not an object")
        metadata, metrics = row.get("metadata"), row.get("metrics")
        if not isinstance(metadata, dict) or not isinstance(metrics, dict):
            raise _fail(board, f"{where} has no metadata or metrics")
        if not isinstance(row.get("id"), str) or number(row.get("rank")) is None:
            raise _fail(board, f"{where} has no id or rank")
        if (
            _label(metadata.get("agent_display")) is None
            and _label(metadata.get("model_display")) is None
        ):
            raise _fail(board, f"{where} names neither agent nor model")
        effort = metadata.get("reasoning_effort")
        if effort is not None and not isinstance(effort, str):
            raise _fail(board, f"{where} reasoning_effort is not text")
        accuracy = number(metrics.get("accuracy"))
        if accuracy is None or not 0 <= accuracy <= 100:
            raise _fail(
                board, f"{where} accuracy {metrics.get('accuracy')!r} is not a 0-100 number"
            )
    return leaderboard, rows


def _names(row: dict[str, Any]) -> tuple[str, str]:
    """(model, agent) as the site labels a row (chartRowLabel): a row without a model is its id."""
    metadata = row["metadata"]
    agent = _label(metadata.get("agent_display")) or ""
    model = _label(metadata.get("model_display")) or ("" if agent else row["id"])
    return model, agent


def default_view(rows: list[dict[str, Any]]) -> dict[str, int]:
    """The site's "best effort" table: row id → its rank there. One row per model and agent
    (highest accuracy, the first served on a tie), ranked over those rows in served order:
    equal accuracy keeps the rank of the row before it (keepBestEffortRows)."""
    ordered = sorted(enumerate(rows), key=lambda pair: (number(pair[1].get("rank")) or 0, pair[0]))
    best: dict[str, dict[str, Any]] = {}
    for _, row in ordered:
        model, agent = _names(row)
        key = f"{model} / {agent}"
        held = best.get(key)
        if held is None or row["metrics"]["accuracy"] > held["metrics"]["accuracy"]:
            best[key] = row
    kept = [row for _, row in ordered if best[" / ".join(_names(row))] is row]
    ranks: dict[str, int] = {}
    last_value: float | None = None
    last_rank = 0
    for place, row in enumerate(kept, start=1):
        value = row["metrics"]["accuracy"]
        last_rank = last_rank if value == last_value else place
        last_value = value
        ranks[row["id"]] = last_rank
    return ranks


def date_key(leaderboard: dict[str, Any]) -> str:
    """The metadata field the board's date column reads (4.0: `date`, 3.0: `release_date`)."""
    for column in leaderboard.get("columns") or []:
        if not isinstance(column, dict) or column.get("type") != "date":
            continue
        accessor = column.get("accessor")
        if isinstance(accessor, str) and accessor.startswith("metadata."):
            return accessor.removeprefix("metadata.")
    return "date"


def _score(
    board: str, row: dict[str, Any], default_rank: int | None, date_field: str = "date"
) -> ScoreRow:
    metadata, metrics = row["metadata"], row["metrics"]
    model, agent = _names(row)
    accuracy = float(metrics["accuracy"])
    half = number(metrics.get("accuracy_ci95_half_width"))
    if half is None:  # the site falls back to 1.96 standard errors
        stderr = number(metrics.get("accuracy_stderr"))
        half = 1.96 * stderr if stderr is not None else None
    effort = metadata.get("reasoning_effort")
    effort = effort.strip() if isinstance(effort, str) and effort.strip() else None
    date = metadata.get(date_field) or metadata.get("date") or metadata.get("release_date")
    extra: dict[str, Any] = {
        "agent": agent,
        "agent_org": _label(metadata.get("agent_org")),
        "agent_url": _url(metadata.get("agent_display")),
        "model_url": _url(metadata.get("model_display")),
        "rank": row["rank"],
        "entry": f"{agent} / {model}",
        "label": f"{agent} · {model}" if agent and model else model or agent,
        "date": date if isinstance(date, str) else None,
        "row_id": row["id"],
    }
    if default_rank is not None:
        extra["default_rank"] = default_rank
    for key in _METRICS_KEPT:
        value = number(metrics.get(key))
        if value is not None:
            extra[key] = value
    for key in _DISPLAY_KEPT:
        if isinstance(metrics.get(key), str):
            extra[key] = metrics[key]
    model_org = _label(metadata.get("model_org"))
    return ScoreRow(
        board=board,
        model_raw=model[:200],
        org=model_org[:80] if model_org else None,
        config=effort[:120] if effort else None,
        metric=METRIC,
        value=accuracy,
        ci_low=max(0.0, accuracy - half) if half is not None else None,
        ci_high=min(100.0, accuracy + half) if half is not None else None,
        extra={k: v for k, v in extra.items() if v is not None},
    )


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    boards: dict[str, Any] = {}
    updated: dict[str, str] = {}
    scores: list[ScoreRow] = []
    for board, package, name in BOARDS:
        data = _download(fetcher, board_url(package, name))
        leaderboard, rows = validate(board, data)
        ranks = default_view(rows)
        field = date_key(leaderboard)
        scores.extend(_score(board, row, ranks.get(row["id"]), field) for row in rows)
        updated[board] = leaderboard["updated_at"][:10]
        boards[board] = {
            "leaderboard": {k: leaderboard.get(k) for k in _LEADERBOARD_KEPT},
            "rows": rows,
        }
    return SiteSnapshot(
        site=SITE,
        release=max(updated.values(), default="") or now.date().isoformat(),
        raw={"boards": boards, "updated": updated},
        rows=scores,
    )
