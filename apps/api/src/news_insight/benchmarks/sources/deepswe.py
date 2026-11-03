"""DeepSWE (Datacurve): pass@1 on 113 software tasks, one row per model + harness + effort.

The site's two leaderboards (its v1.1 / v1 toggle) are plain JSON artifacts; each is stored as
its own board. If either file cannot be read the whole site fails, so the last good snapshot
keeps both boards.
"""

from datetime import datetime
from typing import Any

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
# (board, file): v1.1 first, the board the site opens on
BOARDS = (
    ("v1.1", "https://deepswe.datacurve.ai/artifacts/v1.1/leaderboard-live.json"),
    ("v1", "https://deepswe.datacurve.ai/artifacts/v1/leaderboard-live.json"),
)
_PLOTTED = {"model", "reasoning_effort", "pass_at_1", "ci_lo", "ci_hi"}


def _score(board: str, row: Any) -> ScoreRow | None:
    value = number(row.get("pass_at_1")) if isinstance(row, dict) else None
    model = row.get("model") if isinstance(row, dict) else None
    if value is None or not isinstance(model, str) or not model:
        return None
    effort = row.get("reasoning_effort")
    provider = row.get("provider")
    return ScoreRow(
        board=board,
        model_raw=model,
        org=provider if isinstance(provider, str) and provider else None,
        config=effort if isinstance(effort, str) and effort else None,
        metric="pass_at_1",
        value=value,
        ci_low=number(row.get("ci_lo")),
        ci_high=number(row.get("ci_hi")),
        # cost, tokens, steps, harness, provider...: the axes of the site's own charts
        extra={
            k: v for k, v in row.items() if k not in _PLOTTED and isinstance(v, int | float | str)
        },
    )


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    boards: dict[str, Any] = {}
    scores: list[ScoreRow] = []
    for board, url in BOARDS:
        data = get_json(fetcher, url, JSON_MIME)
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise BenchmarkError(SELECTOR_DRIFT, f"{url}: no rows list")
        found = [score for row in rows if (score := _score(board, row)) is not None]
        if not found:
            raise BenchmarkError(SELECTOR_DRIFT, f"{url}: no usable rows")
        boards[board] = data
        scores += found
    generated = [
        d["generated_at"] for d in boards.values() if isinstance(d.get("generated_at"), str)
    ]
    release = max(g[:10] for g in generated) if generated else now.date().isoformat()
    return SiteSnapshot(site=SITE, release=release, raw={"boards": boards}, rows=scores)
