"""Epoch AI Benchmarking Hub: one zip of CSVs (CC BY 4.0), fetched only when its ETag changes.

`benchmark_data.zip` holds one CSV per benchmark plus the Epoch Capabilities Index; a few boards
are kept (BOARDS). Each board is ranked as epoch.ai's benchmark leaderboards rank it
(getBenchmarkResults in its generated benchmark-page script, read 2026-11-08):
- Epoch-run benchmarks (GPQA Diamond, FrontierMath, SWE-bench Verified): every run's
  `mean_score`, the best run per model version, best first;
- external benchmarks: the column the site plots for it (HLE "Accuracy", ARC-AGI-2 "Score",
  METR "Time horizon" in minutes, ...), the best row per model version, best first;
- the ECI: one row per model, by ECI, best first.
The rank is the place in that list (`extra.default_rank`). The site names a model by the
"Unique display name" of its benchmarked_models.csv (else "Display name", "Model", the
version); that file is read alongside the zip, and if it cannot be read the zip's
model_metadata.csv stands in (display name, else model group, else the version). The ECI board
names a model by the ECI file's own "Display name".
A board's date is its newest run (`Started at`), else its newest model release date.

The request carries the stored ETag (If-None-Match); a 304 means nothing changed and nothing is
downloaded. The zip is read in memory with the standard library.
"""

import csv
import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from news_insight.benchmarks.sources import (
    PARSE_ERROR,
    BenchmarkError,
    NotModified,
    ScoreRow,
    SiteSnapshot,
    get,
)
from news_insight.net.mime import CSV_MIME
from news_insight.net.safe_fetch import SafeFetcher

logger = logging.getLogger(__name__)

SITE = "epoch"
TITLE = "Epoch AI"
SOURCE_URL = "https://epoch.ai/benchmarks"
LICENSE = "CC BY 4.0"
ATTRIBUTION = (
    "Epoch AI, ‘Capabilities & benchmarking’. Published online at epoch.ai. "
    "Retrieved from ‘https://epoch.ai/benchmarks’"
)
DATA_URL = "https://epoch.ai/data/benchmark_data.zip"
NAMES_URL = "https://epoch.ai/data/benchmarked_models.csv"  # the site's model names, 0.3 MB
METRIC = "score"
USES_PREVIOUS = True
ZIP_MIME = frozenset(
    {"application/zip", "application/x-zip-compressed", "application/octet-stream"}
)
MAX_BYTES = 40 * 1024 * 1024  # 2.3 MB today
MAX_MEMBER_BYTES = 8 * 1024 * 1024  # each CSV we read is under 0.2 MB


@dataclass(frozen=True)
class Board:
    key: str
    file: str
    title: str
    kind: str  # "eci", "internal" (Epoch's own runs) or "external"
    column: str = "mean_score"
    unit: str = "percent"  # "percent" (a 0-1 share), "minutes" or "index"
    low: str | None = None
    high: str | None = None
    page: str = ""  # the board's page on epoch.ai


BOARDS = (
    Board(
        "eci",
        "epoch_capabilities_index/eci_scores.csv",
        "ECI",
        "eci",
        "eci",
        "index",
        "eci_ci_low",
        "eci_ci_high",
        "eci",
    ),
    Board("gpqa_diamond", "gpqa_diamond.csv", "GPQA Diamond", "internal", page="gpqa-diamond"),
    Board(
        "frontiermath_tiers_1_3",
        "frontiermath_tiers_1_3_v2.csv",
        "FrontierMath 1–3",
        "internal",
        page="frontiermath-tiers-1-3-v2",
    ),
    Board(
        "frontiermath_tier_4",
        "frontiermath_tier_4_v2.csv",
        "FrontierMath 4",
        "internal",
        page="frontiermath-tier-4-v2",
    ),
    Board("hle", "hle_external.csv", "Humanity's Last Exam", "external", "Accuracy", page="hle"),
    Board(
        "arc_agi_2", "arc_agi_2_external.csv", "ARC-AGI-2", "external", "Score", page="arc-agi-2"
    ),
    Board(
        "swe_bench_verified",
        "swe_bench_verified.csv",
        "SWE-bench Verified",
        "internal",
        page="swe-bench-verified",
    ),
    Board(
        "metr_time_horizons",
        "metr_time_horizons_external.csv",
        "METR Time Horizons",
        "external",
        "Time horizon",
        "minutes",
        "CI_low",
        "CI_high",
        "metr-time-horizons",
    ),
    Board(
        "cursorbench",
        "cursorbench_external.csv",
        "CursorBench",
        "external",
        "Score",
        page="cursorbench",
    ),
    Board("gdpval", "gdpval_external.csv", "GDPval", "external", "Win Rate (%)", page="gdpval"),
)
# columns a board's table or tooltip shows beyond the score, as the CSVs name them
_EXTRA_COLUMNS = {
    "Source": "source",
    "Source link": "source_link",
    "Reasoning level": "reasoning",
    "Cost per task": "cost_per_task",
    "Win + tie rate (%)": "win_tie_rate",
    "Time Horizon (80%)": "time_horizon_80",
    "METR version": "metr_version",
    "Calibration Error": "calibration_error",
    "stderr": "stderr",
}


def _fail(message: str) -> BenchmarkError:
    return BenchmarkError(PARSE_ERROR, f"epoch: {message}")


def _csv(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise _fail(f"{name} is not in the zip") from exc
    if info.file_size > MAX_MEMBER_BYTES:
        raise _fail(f"{name} is {info.file_size} bytes")
    text = archive.read(info).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _float(text: str | None) -> float | None:
    if text is None or not text.strip():
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value == value and abs(value) != float("inf") else None


def _names(archive: zipfile.ZipFile) -> dict[str, dict[str, str]]:
    """model_version → its metadata row (display name, group, organisation, date)."""
    return {
        row["model_version"]: row
        for row in _csv(archive, "model_metadata.csv")
        if row.get("model_version")
    }


def _display(meta: dict[str, str] | None, version: str) -> str:
    if not meta:
        return version
    return (
        meta.get("Unique display name")
        or meta.get("Display name")
        or meta.get("Model")
        or meta.get("display_name")
        or meta.get("model_group")
        or version
    )


def site_names(text: str) -> dict[str, dict[str, str]]:
    """benchmarked_models.csv: id_model_version → its row (the site's own names)."""
    rows = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not rows.fieldnames or "id_model_version" not in rows.fieldnames:
        return {}
    return {row["id_model_version"]: row for row in rows if row.get("id_model_version")}


def _site_names(fetcher: SafeFetcher) -> dict[str, dict[str, str]]:
    """The site's names, or {} (the zip's metadata names stand in) when the file is not there."""
    try:
        response = get(fetcher, NAMES_URL, CSV_MIME, max_bytes=MAX_BYTES)
    except BenchmarkError as exc:
        logger.warning("epoch: model names unavailable (%s), using the zip's metadata", exc)
        return {}
    return site_names(response.content.decode("utf-8", errors="replace"))


def readme(archive: zipfile.ZipFile) -> str:
    try:
        return archive.read("README.md").decode("utf-8", errors="replace")[:4000]
    except KeyError:
        return ""


def rank_board(board: Board, rows: list[dict[str, str]]) -> list[tuple[float, dict[str, str]]]:
    """(value, row) in the site's leaderboard order: the best row per model, best first."""
    if board.kind == "eci":
        seen: set[str] = set()
        found = []
        for row in rows:
            value, name = _float(row.get("eci")), row.get("Model") or ""
            if value is None or not name or name in seen:
                continue
            seen.add(name)
            found.append((value, row))
        return sorted(found, key=lambda pair: -pair[0])
    scored = [(v, row) for row in rows if (v := _float(row.get(board.column))) is not None]
    if board.kind == "internal":  # the site sorts the runs first, then keeps each model's best
        scored.sort(key=lambda pair: -pair[0])
    best: dict[str, tuple[float, dict[str, str]]] = {}
    for value, row in scored:
        version = row.get("Model version") or ""
        if version and (version not in best or value > best[version][0]):
            best[version] = (value, row)
    return sorted(best.values(), key=lambda pair: -pair[0])


def _updated(rows: list[dict[str, str]]) -> str:
    runs = [(row.get("Started at") or "")[:10] for row in rows]
    days = [d for d in runs if d] or [
        (row.get("Release date") or row.get("date") or "")[:10] for row in rows
    ]
    return max((d for d in days if d), default="")


def _board_rows(
    board: Board, ranked: list[tuple[float, dict[str, str]]], names: dict[str, dict[str, str]]
) -> list[ScoreRow]:
    out = []
    for place, (value, row) in enumerate(ranked, start=1):
        if board.kind == "eci":
            version = row.get("Model") or ""
            model = row.get("Display name") or version
            org = row.get("Organization") or None
            released = row.get("date") or None
        else:
            version = row.get("Model version") or ""
            meta = names.get(version)
            model = _display(meta, version)
            org = row.get("Organization") or (meta or {}).get("organization") or None
            released = row.get("Release date") or (meta or {}).get("date") or None
        extra: dict[str, Any] = {
            "model_version": version,
            "unit": board.unit,
            "default_rank": place,
            "entry": version,
            "label": model,
            "release_date": released,
        }
        for column, key in _EXTRA_COLUMNS.items():
            raw = row.get(column)
            if raw:
                extra[key] = number_or_text(raw)
        if board.kind == "eci":
            extra["accessibility"] = row.get("Accessibility group") or None
        out.append(
            ScoreRow(
                board=board.key,
                model_raw=model[:200],
                org=org.split(",")[0].strip()[:80] if org else None,
                config=None,
                metric=METRIC,
                value=value,
                ci_low=_float(row.get(board.low)) if board.low else None,
                ci_high=_float(row.get(board.high)) if board.high else None,
                extra={k: v for k, v in extra.items() if v is not None},
            )
        )
    return out


def number_or_text(raw: str) -> float | str:
    value = _float(raw)
    return value if value is not None else raw.strip()[:300]


def parse(
    content: bytes, site: dict[str, dict[str, str]] | None = None
) -> tuple[dict[str, Any], list[ScoreRow]]:
    """The kept boards of the zip: (raw, score rows). `site`: the site's model names by
    version (benchmarked_models.csv); a version it lacks is named from the zip's metadata."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise _fail("not a zip file") from exc
    with archive:
        names = {**_names(archive), **(site or {})}
        boards: dict[str, list[list[Any]]] = {}
        updated: dict[str, str] = {}
        scores: list[ScoreRow] = []
        for board in BOARDS:
            rows = _csv(archive, board.file)
            if rows and board.column not in rows[0]:
                raise _fail(f"{board.file} has no {board.column!r} column")
            ranked = rank_board(board, rows)
            if not ranked:
                raise _fail(f"{board.file} has no scores")
            scores.extend(_board_rows(board, ranked, names))
            boards[board.key] = [
                [row.get("Model") if board.kind == "eci" else row.get("Model version"), value]
                for value, row in ranked
            ]
            updated[board.key] = _updated(rows)
        notice = readme(archive)
    raw = {
        "boards": boards,
        "titles": {board.key: board.title for board in BOARDS},
        "units": {board.key: board.unit for board in BOARDS},
        "pages": {board.key: f"{SOURCE_URL}/{board.page}" for board in BOARDS},
        "updated": updated,
        "readme": notice,
    }
    return raw, scores


def fetch(
    fetcher: SafeFetcher, now: datetime, previous: dict[str, Any] | None = None
) -> SiteSnapshot:
    etag = previous.get("etag") if isinstance(previous, dict) else None
    headers = {"If-None-Match": etag} if isinstance(etag, str) and etag else None
    response = get(
        fetcher, DATA_URL, ZIP_MIME, headers=headers, max_bytes=MAX_BYTES, not_modified=True
    )
    if response.status_code == 304:
        raise NotModified(f"epoch: ETag {etag} unchanged")
    raw, scores = parse(response.content, _site_names(fetcher))
    raw["etag"] = response.headers.get("etag") or response.headers.get("ETag")
    release = max(raw["updated"].values(), default="") or now.date().isoformat()
    return SiteSnapshot(site=SITE, release=release, raw=raw, rows=scores)
