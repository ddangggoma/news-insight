"""DeepSWE (Datacurve): pass@1 on 113 software tasks, one row per model + harness + effort.

The site's two leaderboards (its v1.1 / v1 toggle) are plain JSON artifacts; each is stored as
its own board. If either file cannot be read the whole site fails, so the last good snapshot
keeps both boards.

The site's chart and table open on a default set of models: those whose best configuration
passes at least 5%, minus a short list it hides until picked in its "Models" menu. Both are
read from the page's leaderboard script and stored as `raw["default_view"]`; when the script
cannot be read the last known values below stand in (the boards themselves are unaffected).
"""

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from news_insight.benchmarks.sources import (
    SELECTOR_DRIFT,
    BenchmarkError,
    ScoreRow,
    SiteSnapshot,
    get,
    get_json,
    number,
)
from news_insight.net.mime import HTML_MIME, JAVASCRIPT_MIME, JSON_MIME
from news_insight.net.safe_fetch import SafeFetcher

logger = logging.getLogger(__name__)

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
# the site's defaults as of 2026-11-04 (live-leaderboard-CCyhM4yo.js), used when its script
# cannot be read
DEFAULT_HIDDEN = (
    "gpt-5-6-terra",
    "gpt-5-4",
    "grok-4-5",
    "kimi-k2-7-code",
    "claude-sonnet-4-6",
    "gemini-3-1-pro-preview",
    "muse-spark-1-1",
)
DEFAULT_MIN_BEST = 0.05
_LEADERBOARD_SCRIPT = re.compile(r"assets/live-leaderboard-[\w-]+\.js")
# `const ft=.05,mt=new Set(["gpt-5-6-terra",...])`: the minimum best pass rate, then the set
_DEFAULTS = re.compile(r"=(0?\.\d+),[\w$]+=new Set\(\[((?:\"[^\"]*\",?)*)\]\)")


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


def default_view(script: str) -> dict[str, Any] | None:
    """{"min_best": 0.05, "hidden": [...]} from the site's leaderboard script, or None."""
    found = _DEFAULTS.search(script)
    if found is None:
        return None
    hidden = re.findall(r'"([^"]*)"', found.group(2))
    return {"min_best": float(found.group(1)), "hidden": sorted(set(hidden))}


def fallback_view() -> dict[str, Any]:
    return {"min_best": DEFAULT_MIN_BEST, "hidden": sorted(DEFAULT_HIDDEN)}


def _site_defaults(fetcher: SafeFetcher) -> dict[str, Any]:
    """The default model set as the page's script states it, else the last known one."""
    try:
        page = get(fetcher, SOURCE_URL, HTML_MIME).content.decode("utf-8", errors="replace")
        script = _LEADERBOARD_SCRIPT.search(page)
        if script is not None:
            url = urljoin(SOURCE_URL, script.group(0))
            body = get(fetcher, url, JAVASCRIPT_MIME).content.decode("utf-8", errors="replace")
            found = default_view(body)
            if found is not None:
                return found
        logger.warning("deepswe: default model set not found in the page, using the last known")
    except BenchmarkError as exc:
        logger.warning("deepswe: page script unreadable (%s), using the last known defaults", exc)
    return fallback_view()


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
    # each board's own "updated" date, as the site prints it above the chart
    updated = {
        board: data["generated_at"][:10]
        for board, data in boards.items()
        if isinstance(data.get("generated_at"), str)
    }
    raw = {"boards": boards, "default_view": _site_defaults(fetcher), "updated": updated}
    return SiteSnapshot(site=SITE, release=release, raw=raw, rows=scores)
