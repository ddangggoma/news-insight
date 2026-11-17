"""Vending-Bench 2 (Andon Labs): a model runs a simulated vending-machine business for a year
and is scored on its bank balance at the end. The numbers are read from Epoch AI's copy
(`external_benchmarks/vending_bench_2.csv`, CC BY 4.0), so both are credited: Andon Labs made
the benchmark, Epoch AI distributes the table.

Read 2026-11-13. andonlabs.com/evals/vending-bench-2 opens its "Current leaderboard" (average
across runs) on rank, model and money balance ("$16,484.21"), best first, ten rows and a
"Show more". Epoch's file has one row per model version with `Score` (the balance in dollars),
`Name` (Andon's own name for the entry), the release date and the organisation; it carries no
± and may trail Andon's page by a few entries. The best row per model version is kept, best
first, and its place is `extra.default_rank`.

A model is named as epoch.py names it on its other boards (the row's "Unique display name",
else "Display name", "Model", the version), so one model reads the same across the Epoch
boards and this one; Andon's `Name` is kept as `extra.label`, which the card prints.
"""

import csv
import io
from datetime import datetime
from typing import Any

from news_insight.benchmarks.sources import (
    PARSE_ERROR,
    BenchmarkError,
    ScoreRow,
    SiteSnapshot,
    epoch,
    get,
)
from news_insight.net.mime import CSV_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "vending_bench"
TITLE = "Vending-Bench 2"
SOURCE_URL = "https://andonlabs.com/evals/vending-bench-2"
LICENSE = "CC BY 4.0 (Epoch AI 배포본)"
ATTRIBUTION = (
    "Vending-Bench 2 (Andon Labs); 데이터 배포 Epoch AI, ‘Capabilities & benchmarking’, "
    "epoch.ai/benchmarks"
)
DATA_URL = "https://epoch.ai/data/external_benchmarks/vending_bench_2.csv"
BOARD = "main"
METRIC = "money_balance"
MAX_BYTES = 8 * 1024 * 1024  # 0.1 MB today
_COLUMNS = ("Model version", "Score")


def _fail(message: str) -> BenchmarkError:
    return BenchmarkError(PARSE_ERROR, f"vending-bench: {message}")


def _float(text: str | None) -> float | None:
    if text is None or not text.strip():
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value == value and abs(value) != float("inf") else None


def ranked(text: str) -> list[tuple[float, dict[str, str]]]:
    """(balance, row): the best row per model version, best first."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fields = reader.fieldnames or []
    for column in _COLUMNS:
        if column not in fields:
            raise _fail(f"no {column!r} column")
    best: dict[str, tuple[float, dict[str, str]]] = {}
    for row in reader:
        version, value = (row.get("Model version") or "").strip(), _float(row.get("Score"))
        if not version or value is None:
            continue
        if version not in best or value > best[version][0]:
            best[version] = (value, row)
    if not best:
        raise _fail("no scores")
    return sorted(best.values(), key=lambda pair: -pair[0])


def parse(text: str) -> tuple[dict[str, Any], list[ScoreRow]]:
    rows = ranked(text)
    scores = []
    for place, (value, row) in enumerate(rows, start=1):
        version = row["Model version"].strip()
        model = epoch._display(row, version)
        org = (row.get("Organization") or "").split(",")[0].strip()
        released = (row.get("Version release date") or row.get("Release date") or "")[:10]
        extra: dict[str, Any] = {
            "default_rank": place,
            "entry": version,
            "label": (row.get("Name") or "").strip() or model,
            "model_version": version,
            "release_date": released or None,
            "notes": (row.get("Notes") or "").strip()[:300] or None,
        }
        scores.append(
            ScoreRow(
                board=BOARD,
                model_raw=model[:200],
                org=org[:80] or None,
                config=None,
                metric=METRIC,
                value=value,
                extra={k: v for k, v in extra.items() if v is not None},
            )
        )
    days = [s.extra["release_date"] for s in scores if "release_date" in s.extra]
    raw = {
        "rows": [[row["Model version"].strip(), value] for value, row in rows],
        # the file states no date of its own: the newest model release it lists stands in
        "updated": {BOARD: max(days, default="")},
    }
    return raw, scores


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    response = get(fetcher, DATA_URL, CSV_MIME, max_bytes=MAX_BYTES)
    raw, scores = parse(response.content.decode("utf-8", errors="replace"))
    return SiteSnapshot(
        site=SITE,
        release=raw["updated"][BOARD] or now.date().isoformat(),
        raw=raw,
        rows=scores,
    )
