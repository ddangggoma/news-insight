"""DeepSWE (Datacurve): pass@1 on 113 software tasks, one row per model + harness + effort."""

from datetime import datetime

from news_insight.benchmarks.sources import (
    SELECTOR_DRIFT,
    BenchmarkError,
    ScoreRow,
    SiteSnapshot,
    get_json,
    number,
)
from news_insight.net.mime import JSON_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "deepswe"
TITLE = "DeepSWE"
SOURCE_URL = "https://deepswe.datacurve.ai/"
LICENSE = "공개 JSON, 별도 라이선스 표기 없음"
ATTRIBUTION = "DeepSWE (Datacurve)"
DATA_URL = "https://deepswe.datacurve.ai/artifacts/v1/leaderboard-live.json"
BOARD = "v1.1"  # the file carries no version field, only a prose scope
_PLOTTED = {"model", "reasoning_effort", "pass_at_1", "ci_lo", "ci_hi"}


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    data = get_json(fetcher, DATA_URL, JSON_MIME)
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise BenchmarkError(SELECTOR_DRIFT, f"{DATA_URL}: no rows list")
    scores: list[ScoreRow] = []
    for row in rows:
        value = number(row.get("pass_at_1")) if isinstance(row, dict) else None
        model = row.get("model") if isinstance(row, dict) else None
        if value is None or not isinstance(model, str) or not model:
            continue
        effort = row.get("reasoning_effort")
        scores.append(
            ScoreRow(
                board=BOARD,
                model_raw=model,
                org=None,
                config=effort if isinstance(effort, str) and effort else None,
                metric="pass_at_1",
                value=value,
                ci_low=number(row.get("ci_lo")),
                ci_high=number(row.get("ci_hi")),
                # cost, tokens, steps, harness...: the axes of the site's own charts
                extra={
                    k: v
                    for k, v in row.items()
                    if k not in _PLOTTED and isinstance(v, int | float | str)
                },
            )
        )
    if not scores:
        raise BenchmarkError(SELECTOR_DRIFT, f"{DATA_URL}: no usable rows")
    generated = data.get("generated_at")
    release = generated[:10] if isinstance(generated, str) and generated else now.date().isoformat()
    return SiteSnapshot(site=SITE, release=release, raw=data, rows=scores)
