"""DeepSWE (Datacurve): pass@1 on 113 software tasks, one row per model + harness + effort.

The site's two leaderboards (its v1.1 / v1 toggle) are plain JSON artifacts; each is stored as
its own board. If either file cannot be read the whole site fails, so the last good snapshot
keeps both boards.

The site's chart and table open on a default set of models: those whose best configuration
passes at least 5%, minus a short list it hides until picked in its "Models" menu. Both are
read from the page's leaderboard script and stored as `raw["default_view"]`.

The page also re-prices a few models' costs before it draws them: for a model whose price
changed since its runs, every `*cost_usd` field is scaled by (the run's tokens at today's
prices) / (the same tokens at the old prices). The table of old and new prices is read from the
page's main script (`raw["repricing"]`) and applied to the rows' costs, so the reader shows the
costs the site shows; the stored boards stay as the site serves them. When either script cannot
be read, the last known values below stand in (the boards themselves are unaffected).
"""

import json
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
# the page's repricing table as of 2026-11-04 (index-DYZDg9jy.js), $ per million tokens: a
# model's own {from, to} prices, or one pair per board
_P = dict[str, float]
DEFAULT_REPRICING: dict[str, Any] = {
    "glm-5-3-flash": {
        "from": {"input": 0.15, "cached": 0.03, "output": 0.5},
        "to": {"input": 0.075, "cached": 0.015, "output": 0.25},
    },
    "gpt-5-6-luna": {
        "from": {"input": 1, "cached": 0.1, "output": 6},
        "to": {"input": 0.2, "cached": 0.02, "output": 1.2},
    },
    "gpt-5-6-terra": {
        "from": {"input": 2.5, "cached": 0.25, "output": 15},
        "to": {"input": 2, "cached": 0.2, "output": 12},
    },
    "gpt-5-6-sol": {
        "from": {"input": 5, "cached": 0.5, "output": 30},
        "to": {"input": 4, "cached": 0.4, "output": 20},
    },
    "deepseek-v4-pro": {
        "v1": {
            "from": {"input": 1.74, "cached": 0.0145, "output": 3.48},
            "to": {"input": 0.435, "cached": 0.003625, "output": 0.87},
        },
        "v1.1": {
            "from": {"input": 0.435, "cached": 0.003625, "output": 0.87},
            "to": {"input": 1.32, "cached": 0.044, "output": 3.96},
        },
    },
    "deepseek-v4-flash": {
        "from": {"input": 0.14, "cached": 0.0028, "output": 0.28},
        "to": {"input": 0.44, "cached": 0.014, "output": 1.32},
    },
    "gemini-3-6-flash": {
        "from": {"input": 1.5, "cached": 0.15, "output": 7.5},
        "to": {"input": 0.75, "cached": 0.075, "output": 3.75},
    },
}
_LEADERBOARD_SCRIPT = re.compile(r"assets/live-leaderboard-[\w-]+\.js")
_MAIN_SCRIPT = re.compile(r"assets/index-[\w-]+\.js")
# `const ft=.05,mt=new Set(["gpt-5-6-terra",...])`: the minimum best pass rate, then the set
_DEFAULTS = re.compile(r"=(0?\.\d+),[\w$]+=new Set\(\[((?:\"[^\"]*\",?)*)\]\)")
# `L6={"glm-5-3-flash":{from:{...},to:{...}},...},D6=/(^|_)cost_usd$/`: the table, then the
# pattern of the fields it scales
_REPRICING = re.compile(r"=(\{\"[^;]*?\}\}),[\w$]+=/\(\^\|_\)cost_usd\$/")
_COST_FIELD = re.compile(r"(^|_)cost_usd$")
# the token fields the page prices a run with, the first set a row has (its `z6`)
_TOKEN_FIELDS = (
    ("n_input_tokens", "n_cache_tokens", "n_output_tokens"),
    ("mean_input_tokens", "mean_cache_tokens", "mean_output_tokens"),
    ("total_prompt_tokens", "total_cached_tokens", "total_completion_tokens"),
    ("prompt_tokens", "cached_tokens", "completion_tokens"),
)


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


def repricing(script: str) -> dict[str, Any] | None:
    """The page's repricing table ({model: {from, to}} or {model: {board: {from, to}}}) from its
    main script, or None. The script writes it as a JS object literal (bare keys, `.15`)."""
    found = _REPRICING.search(script)
    if found is None:
        return None
    text = re.sub(r"([{,])([A-Za-z_$][\w$]*):", r'\1"\2":', found.group(1))
    text = re.sub(r"([:,\[])(-?)\.(\d)", r"\g<1>\g<2>0.\3", text)
    try:
        table = json.loads(text)
    except ValueError:
        return None
    return table if isinstance(table, dict) else None


def _prices(entry: Any, board: str) -> tuple[_P, _P] | None:
    """A model's (old, new) prices on a board: its own pair, else the board's."""
    if not isinstance(entry, dict):
        return None
    if "from" not in entry or "to" not in entry:
        entry = entry.get(board)
        if not isinstance(entry, dict) or "from" not in entry or "to" not in entry:
            return None
    old, new = entry["from"], entry["to"]
    if not isinstance(old, dict) or not isinstance(new, dict):
        return None
    return old, new


def _priced(prices: _P, tokens: _P) -> float:
    def at(key: str) -> float:
        value = prices.get(key)
        return float(value) if isinstance(value, int | float) else 0.0

    uncached = tokens["input"] - tokens["cached"]
    cached, output = tokens["cached"], tokens["output"]
    return uncached * at("input") + cached * at("cached") + output * at("output")


def cost_factor(row: dict[str, Any], board: str, table: dict[str, Any]) -> float | None:
    """What the page multiplies a row's costs by (its `q6`), or None when it leaves them."""
    model = row.get("model")
    if not isinstance(model, str):
        return None
    key = re.sub(r"[._]", "-", model.split("/")[-1]).lower()
    pair = _prices(table.get(key), board)
    if pair is None:
        return None
    old, new = pair
    for fields in _TOKEN_FIELDS:
        given, cached, out = (number(row.get(field)) for field in fields)
        if given is not None and out is not None:
            tokens = {"input": given, "cached": cached or 0.0, "output": out}
            before = _priced(old, tokens)
            return _priced(new, tokens) / before if before > 0 else None
    # no token counts: only a price change by one factor across the board can be applied
    ratios = [
        float(new[k]) / float(old[k])
        for k in ("input", "cached", "output")
        if isinstance(new.get(k), int | float) and isinstance(old.get(k), int | float) and old[k]
    ]
    if len(ratios) == 3 and max(ratios) - min(ratios) < 1e-9:
        return ratios[0]
    return None


def repriced(row: dict[str, Any], board: str, table: dict[str, Any]) -> dict[str, Any]:
    """The row with its `*cost_usd` fields at the site's current prices (unchanged if none)."""
    factor = cost_factor(row, board, table)
    if factor is None:
        return row
    return {
        k: v * factor
        if _COST_FIELD.search(k) and isinstance(v, int | float) and not isinstance(v, bool)
        else v
        for k, v in row.items()
    }


def _text(fetcher: SafeFetcher, url: str, mime: frozenset[str]) -> str:
    return get(fetcher, url, mime).content.decode("utf-8", errors="replace")


def _page_rules(fetcher: SafeFetcher) -> tuple[dict[str, Any], dict[str, Any]]:
    """(default view, repricing table) as the page's scripts state them; whatever cannot be
    read is the last known one, and logged."""
    view: dict[str, Any] | None = None
    table: dict[str, Any] | None = None
    try:
        page = _text(fetcher, SOURCE_URL, HTML_MIME)
        for pattern, name in ((_LEADERBOARD_SCRIPT, "view"), (_MAIN_SCRIPT, "table")):
            script = pattern.search(page)
            if script is None:
                continue
            body = _text(fetcher, urljoin(SOURCE_URL, script.group(0)), JAVASCRIPT_MIME)
            if name == "view":
                view = default_view(body)
            else:
                table = repricing(body)
    except BenchmarkError as exc:
        logger.warning("deepswe: page scripts unreadable (%s), using the last known rules", exc)
    if view is None:
        logger.warning("deepswe: default model set not found, using the last known")
        view = fallback_view()
    if table is None:
        logger.warning("deepswe: cost repricing table not found, using the last known")
        table = DEFAULT_REPRICING
    return view, table


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    boards: dict[str, Any] = {}
    for board, url in BOARDS:
        data = get_json(fetcher, url, JSON_MIME)
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise BenchmarkError(SELECTOR_DRIFT, f"{url}: no rows list")
        if not any(_score(board, row) is not None for row in rows):
            raise BenchmarkError(SELECTOR_DRIFT, f"{url}: no usable rows")
        boards[board] = data
    view, table = _page_rules(fetcher)
    scores = [
        score
        for board, data in boards.items()
        for row in data["rows"]
        if (score := _score(board, repriced(row, board, table) if isinstance(row, dict) else row))
        is not None
    ]
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
    raw = {"boards": boards, "default_view": view, "repricing": table, "updated": updated}
    return SiteSnapshot(site=SITE, release=release, raw=raw, rows=scores)
