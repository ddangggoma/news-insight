"""Vals Index (vals.ai): agentic model performance across finance, coding, legal and tax tasks,
weighted by each sector's share of US GDP.

The page is an Astro site; its data is in the `props` of two `<astro-island>` elements, in
Astro's serialized form (every value a `[type, value]` pair: 0 plain, 1 array):
- the ranking section (`regularLeaderboardItems`, `openSourceLeaderboardItems`): each model's
  display name, company, position, accuracy and its four sector scores;
- the chart's `benchmarkView`: `tasks.overall` by model key with accuracy, stderr, latency,
  cost per test and average tokens, and `metadata` (version, the day it was updated).

Read 2026-11-13. The page's default view, top to bottom: a bar ranking that opens on "Showing
best model from each lab" (the best model of every company, best first; a view option shows
all); an accuracy-against-cost chart; then the table: Rank, Model, Accuracy ("71.31%"),
Cost / Test ("$17.94"), Tokens / Test (average input + output tokens, "31.31m") and
Duration / Test (the latency in seconds as "43m42s" or "1h26m"). The table's rank is the
ranking's `position`, stored as `extra.default_rank`.

Licence: CC BY 4.0 (the page's JSON-LD Dataset record). robots.txt allows the page.
"""

import html as html_lib
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
from news_insight.net.mime import HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "vals"
TITLE = "Vals Index"
SOURCE_URL = "https://www.vals.ai/benchmarks/vals_index"
LICENSE = "CC BY 4.0"
ATTRIBUTION = "Vals AI, ‘Vals Index’ (vals.ai)"
BOARD = "vals_index"
METRIC = "accuracy"
MAX_BYTES = 8 * 1024 * 1024  # 0.8 MB today

_ISLAND = re.compile(r"<astro-island\b[^>]*?\sprops=\"([^\"]*)\"", re.DOTALL)
_TOKEN_KEYS = ("input_tokens", "output_tokens", "reasoning_tokens")


def _fail(message: str) -> BenchmarkError:
    return BenchmarkError(PARSE_ERROR, f"vals: {message}")


def revive(value: Any) -> Any:
    """Astro's serialized props back to plain JSON: `[0, x]` is x (objects recursed), `[1, xs]`
    an array of such pairs, `[0]` an undefined; the other types (dates, maps, …) keep their
    raw value."""
    if not isinstance(value, list) or not value or isinstance(value[0], bool):
        return value
    if not isinstance(value[0], int):
        return value
    if len(value) == 1:
        return None
    if len(value) != 2:
        return value
    kind, inner = value
    if kind == 0:
        return {k: revive(v) for k, v in inner.items()} if isinstance(inner, dict) else inner
    if kind == 1 and isinstance(inner, list):
        return [revive(item) for item in inner]
    return inner


def islands(page: str) -> list[dict[str, Any]]:
    """The props of every astro-island on the page that decode to an object."""
    found = []
    for match in _ISLAND.finditer(page):
        try:
            props = json.loads(html_lib.unescape(match.group(1)))
        except ValueError:
            continue
        if isinstance(props, dict):
            found.append({key: revive(value) for key, value in props.items()})
    return found


def parse(page: str) -> tuple[dict[str, Any], list[ScoreRow]]:
    """(raw, score rows) of the page: one row per ranked model."""
    found = islands(page)
    ranking = next((p for p in found if isinstance(p.get("regularLeaderboardItems"), list)), None)
    chart = next((p for p in found if isinstance(p.get("benchmarkView"), dict)), None)
    if ranking is None or chart is None:
        raise BenchmarkError(SELECTOR_DRIFT, "vals: the page carries no ranking or chart data")
    view = chart["benchmarkView"]
    tasks = view.get("tasks")
    overall = tasks.get("overall") if isinstance(tasks, dict) else None
    metadata = view.get("metadata")
    if not isinstance(overall, dict) or not isinstance(metadata, dict):
        raise _fail("benchmarkView has no overall task or metadata")
    by_slug = {key.replace("/", "_"): key for key in overall if isinstance(key, str)}
    open_items = ranking.get("openSourceLeaderboardItems")
    open_slugs = {
        item.get("slug")
        for item in (open_items if isinstance(open_items, list) else [])
        if isinstance(item, dict)
    }
    items = ranking["regularLeaderboardItems"]
    if not items:
        raise _fail("the ranking is empty")
    kept: list[dict[str, Any]] = []
    scores: list[ScoreRow] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise _fail(f"ranking item {index} is not an object")
        name, slug = item.get("model"), item.get("slug")
        position = number(item.get("position"))
        if not isinstance(name, str) or not name.strip() or not isinstance(slug, str):
            raise _fail(f"ranking item {index} has no model or slug")
        if position is None:
            raise _fail(f"ranking item {index} has no position")
        key = by_slug.get(slug)
        result = overall.get(key) if key else None
        result = result if isinstance(result, dict) else {}
        accuracy = number(result.get("accuracy"))
        if accuracy is None:
            try:
                accuracy = float(str(item.get("accuracy")))  # the ranking sends it as text
            except (TypeError, ValueError) as exc:
                raise _fail(f"ranking item {index} has no accuracy") from exc
        company = item.get("company")
        company = company.strip() if isinstance(company, str) and company.strip() else None
        tokens_in = number(result.get("avg_input_tokens"))
        tokens_out = number(result.get("avg_output_tokens"))
        sections = [
            {"label": s["label"], "score": number(s.get("score"))}
            for s in item.get("sections") or []
            if isinstance(s, dict) and isinstance(s.get("label"), str)
        ]
        cost = number(result.get("cost_per_test"))
        latency = number(result.get("latency"))
        extra: dict[str, Any] = {
            "default_rank": int(position) if position.is_integer() else position,
            "entry": key or slug,
            "label": name.strip(),
            "model_key": key,
            "stderr": number(result.get("stderr")),
            "cost_per_test": cost if cost is not None else number(item.get("cost")),
            "latency": latency if latency is not None else number(item.get("latency")),
            "tokens_per_test": (
                tokens_in + tokens_out if tokens_in is not None and tokens_out is not None else None
            ),
            "open_weights": slug in open_slugs or None,
            "sections": sections or None,
        }
        totals = result.get("token_totals")
        if isinstance(totals, dict):
            for token_key in _TOKEN_KEYS:
                extra[token_key] = number(totals.get(token_key))
        scores.append(
            ScoreRow(
                board=BOARD,
                model_raw=name.strip()[:200],
                org=company[:80] if company else None,
                config=None,
                metric=METRIC,
                value=accuracy,
                extra={k: v for k, v in extra.items() if v is not None},
            )
        )
        kept.append({"slug": slug, "model": name, "company": company, "position": position})
    updated = metadata.get("updated")
    updated = updated[:10] if isinstance(updated, str) else ""
    raw = {
        "version": metadata.get("version"),
        "tasks": metadata.get("tasks"),
        "ranking": kept,
        "overall": {key: overall[key] for key in sorted(by_slug.values())},
        "open": sorted(slug for slug in open_slugs if isinstance(slug, str)),
        "updated": {BOARD: updated},
    }
    return raw, scores


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    response = get(fetcher, SOURCE_URL, HTML_MIME, max_bytes=MAX_BYTES)
    raw, scores = parse(response.content.decode("utf-8", errors="replace"))
    return SiteSnapshot(
        site=SITE,
        release=raw["updated"][BOARD] or now.date().isoformat(),
        raw=raw,
        rows=scores,
    )
