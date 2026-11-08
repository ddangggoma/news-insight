"""OSWorld 2.0 (XLANG Lab): long-horizon computer-use tasks, one static JSON of results.

The site's leaderboard script (static/js/leaderboard.js) opens on: the "Foundation E2E GUI" tab
(rows whose modelType is e2e or unset), the file's default step budget (500), its default
release version ("all") and dataset scope ("full"; a row without a scope is the file's default
result scope), sorted by its default metric (binary accuracy) best first, ties broken by partial
score, then cost per task (cheapest first), then model name, then the newer release. The rank is
the place in that list. The `official` flag is not a filter there, so it is not one here either
(it is kept on the rows). Each row the default table shows carries `extra.default_rank`.
Read from the page script 2026-11-08.
"""

from datetime import datetime
from typing import Any

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

SITE = "osworld"
TITLE = "OSWorld 2.0"
SOURCE_URL = "https://osworld-v2.xlang.ai/"
LICENSE = "Apache-2.0 (xlang-ai/OSWorld-V2 저장소)"
ATTRIBUTION = "OSWorld 2.0 (XLANG Lab, HKU)"
DATA_URL = "https://osworld-v2.xlang.ai/static/data/leaderboard/official-results.json"
BOARD = "main"
METRIC = "binary_accuracy"
# the script's COMPANY_BY_MODEL_FAMILY: the organisation of a row that names none
COMPANY_BY_MODEL_FAMILY = {
    "Claude": "Anthropic",
    "GPT": "OpenAI",
    "Qwen": "Alibaba",
    "MiniMax": "MiniMax",
    "Kimi": "Moonshot AI",
}
_SORT_METRICS = {"binaryAccuracy", "partialScore", "estimatedCostUsd"}


def _fail(message: str) -> BenchmarkError:
    return BenchmarkError(PARSE_ERROR, f"osworld: {message}")


def validate(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise _fail("no results list")
    if not isinstance(data.get("updatedAt"), str):
        raise _fail("no updatedAt")
    metric = data.get("defaultMetric", "binaryAccuracy")
    if metric not in _SORT_METRICS:
        raise _fail(f"default metric {metric!r} is not one the script sorts by")
    rows: list[dict[str, Any]] = data["results"]
    if not rows:
        raise _fail("no results")
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("model"), str) or not row["model"]:
            raise _fail(f"result {index} has no model")
        if number(row.get("binaryAccuracy")) is None:
            raise _fail(f"result {index} has no binaryAccuracy")
    return rows


def release_version(data: dict[str, Any], row: dict[str, Any]) -> str:
    """getRowReleaseVersion."""
    return str(
        row.get("releaseVersion")
        or row.get("taskVersion")
        or data.get("defaultResultReleaseVersion")
        or data.get("taskVersion")
        or "—"
    )


def dataset_scope(data: dict[str, Any], row: dict[str, Any]) -> str:
    return str(
        row.get("datasetScope")
        or row.get("scope")
        or data.get("defaultResultDatasetScope")
        or "full"
    )


def company(row: dict[str, Any]) -> str | None:
    """getCompanyName."""
    if row.get("company"):
        return str(row["company"])
    family = row.get("modelFamily")
    return (
        COMPANY_BY_MODEL_FAMILY.get(family, family) if isinstance(family, str) and family else None
    )


def cost_per_task(data: dict[str, Any], row: dict[str, Any]) -> float | None:
    """The table's "Cost / task": costPerTaskUsd, else the run's estimated cost over the set."""
    direct = number(row.get("costPerTaskUsd"))
    if direct is not None:
        return direct
    total = number(row.get("estimatedCostUsd"))
    size = number(data.get("datasetSize")) or 108
    return total / size if total is not None else None


def _sort_value(row: dict[str, Any], key: str, ascending: bool) -> float:
    value = number(row.get(key))
    if value is None:
        return float("inf") if ascending else float("-inf")
    return value


def default_view(data: dict[str, Any]) -> list[int]:
    """Indexes of the results the site's table opens on, in its order."""
    budget = data.get("defaultStepBudget") or 500
    version = data.get("defaultReleaseVersion") or "all"
    scope = data.get("defaultDatasetScope") or "full"
    metric = data.get("defaultMetric") or "binaryAccuracy"
    ascending = metric == "estimatedCostUsd"
    shown = []
    for index, row in enumerate(data["results"]):
        scopes = row.get("availableScopes")
        if (row.get("modelType") or "e2e") != "e2e" or row.get("stepBudget") != budget:
            continue
        if version != "all" and release_version(data, row) != version:
            continue
        if dataset_scope(data, row) != scope and not (isinstance(scopes, list) and scope in scopes):
            continue
        shown.append(index)

    def key(index: int) -> tuple[Any, ...]:
        row = data["results"][index]
        first = _sort_value(row, metric, ascending)
        return (
            first if ascending else -first,
            -_sort_value(row, "binaryAccuracy", False),
            -_sort_value(row, "partialScore", False),
            _sort_value(row, "estimatedCostUsd", True),
            str(row.get("model") or "").casefold(),
        )

    # the newest release wins the last tie: sort on it first (descending), then the rest (stable)
    shown.sort(key=lambda i: release_version(data, data["results"][i]), reverse=True)
    shown.sort(key=key)
    return shown


def _score(data: dict[str, Any], row: dict[str, Any], default_rank: int | None) -> ScoreRow:
    reasoning = row.get("reasoning")
    reasoning = reasoning if isinstance(reasoning, str) and reasoning else None
    version, scope = release_version(data, row), dataset_scope(data, row)
    tool = row.get("toolSetting")
    extra: dict[str, Any] = {
        "partial_score": number(row.get("partialScore")),
        "tool_setting": tool if isinstance(tool, str) else None,
        "step_budget": number(row.get("stepBudget")),
        "release_version": version,
        "dataset_scope": scope,
        "model_type": row.get("modelType") or "e2e",
        "official": row.get("official") if isinstance(row.get("official"), bool) else None,
        "cost_per_task": cost_per_task(data, row),
        "output_tokens_per_task": number(row.get("outputTokensPerTask")),
        "agent_name": row.get("agentName"),
        "base_planner_model": row.get("basePlannerModel"),
        "trajectory_url": row.get("trajectoryUrl"),
        "entry": "|".join(
            str(part)
            for part in (
                row["model"],
                reasoning,
                tool,
                row.get("stepBudget"),
                version,
                scope,
                row.get("modelType") or "e2e",
            )
        ),
        "label": f"{row['model']} ({reasoning})" if reasoning else row["model"],
        "default_rank": default_rank,
    }
    org = company(row)
    return ScoreRow(
        board=BOARD,
        model_raw=row["model"][:200],
        org=org[:80] if org else None,
        config=reasoning[:120] if reasoning else None,
        metric=METRIC,
        value=float(row["binaryAccuracy"]),
        extra={k: v for k, v in extra.items() if v is not None},
    )


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    data = get_json(fetcher, DATA_URL, JSON_MIME)
    rows = validate(data)
    order = {index: place for place, index in enumerate(default_view(data), start=1)}
    scores = [_score(data, row, order.get(index)) for index, row in enumerate(rows)]
    updated = data["updatedAt"][:10]
    return SiteSnapshot(
        site=SITE,
        release=updated or now.date().isoformat(),
        raw={"data": data, "updated": {BOARD: updated}},
        rows=scores,
    )
