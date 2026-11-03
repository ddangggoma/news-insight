"""Artificial Analysis: intelligence indices, prices and speed per model (API key required)."""

from datetime import datetime
from typing import Any

from news_insight.benchmarks.sources import (
    CONFIG_ERROR,
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
from news_insight.secrets import SecretError, secret_value

SITE = "artificial_analysis"
TITLE = "Artificial Analysis"
SOURCE_URL = "https://artificialanalysis.ai/"
LICENSE = "Artificial Analysis API 이용약관 (모든 요금제에서 출처 표기 필수)"
ATTRIBUTION = "Artificial Analysis (artificialanalysis.ai)"
SECRET = "ARTIFICIAL_ANALYSIS_KEY"
API_URL = "https://artificialanalysis.ai/api/v2/language/models"
BOARD = "language"
MAX_PAGES = 20
# per-model objects whose numeric fields are metrics, named as the API names them
_METRIC_GROUPS = ("evaluations", "pricing", "performance")


def has_key() -> bool:
    try:
        secret_value(SECRET)
    except SecretError:
        return False
    return True


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    try:
        key = secret_value(SECRET)
    except SecretError as exc:
        raise BenchmarkError(CONFIG_ERROR, str(exc)) from exc
    models: list[dict[str, Any]] = []
    version: Any = None
    for page in range(1, MAX_PAGES + 1):
        url = API_URL if page == 1 else f"{API_URL}?page={page}"
        data = get_json(fetcher, url, JSON_MIME, headers={"x-api-key": key})
        batch = data.get("data") if isinstance(data, dict) else None
        if not isinstance(batch, list):
            raise BenchmarkError(SELECTOR_DRIFT, f"{url}: no data list")
        models.extend(m for m in batch if isinstance(m, dict))
        version = data.get("intelligence_index_version", version)
        if not (data.get("pagination") or {}).get("has_more"):
            break
    scores = [row for model in models for row in _model_rows(model)]
    if not scores:
        raise BenchmarkError(SELECTOR_DRIFT, f"{API_URL}: no usable models")
    release = f"v{version}" if version is not None else now.date().isoformat()
    raw = {"intelligence_index_version": version, "data": models}
    return SiteSnapshot(site=SITE, release=release, raw=raw, rows=scores)


def _model_rows(model: dict[str, Any]) -> list[ScoreRow]:
    name = model.get("name")
    if not isinstance(name, str) or not name:
        return []
    creator = model.get("model_creator")
    org = creator.get("name") if isinstance(creator, dict) else None
    config = config_from_name(name)
    extra = _extra(model)
    rows: list[ScoreRow] = []
    for group in _METRIC_GROUPS:
        fields = model.get(group)
        for metric, raw_value in (fields if isinstance(fields, dict) else {}).items():
            value = number(raw_value)  # null = not measured
            if value is not None:
                rows.append(
                    ScoreRow(
                        board=BOARD,
                        model_raw=name,
                        org=org if isinstance(org, str) else None,
                        config=config,
                        metric=metric,
                        value=value,
                        extra=dict(extra),
                    )
                )
    return rows


def _extra(model: dict[str, Any]) -> dict[str, Any]:
    """What the site's table shows next to the numbers."""
    extra: dict[str, Any] = {}
    for key in ("slug", "release_date", "reasoning_model", "context_window_tokens"):
        if model.get(key) is not None:
            extra[key] = model[key]
    licensing = model.get("licensing")
    if isinstance(licensing, dict) and licensing.get("is_open_weights") is not None:
        extra["is_open_weights"] = licensing["is_open_weights"]
    params = model.get("parameters")
    if isinstance(params, dict):
        extra.update({f"parameters_{k}": v for k, v in params.items() if number(v) is not None})
    cost = model.get("artificial_analysis_intelligence_index_cost")
    per_task = cost.get("cost_per_task") if isinstance(cost, dict) else None
    if isinstance(per_task, dict) and number(per_task.get("total_cost")) is not None:
        extra["index_cost_per_task"] = per_task["total_cost"]
    return extra
