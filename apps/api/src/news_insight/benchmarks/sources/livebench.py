"""LiveBench: contamination-free LLM benchmark; one CSV of category scores per release date."""

import csv
import io
import json
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

from news_insight.benchmarks.sources import (
    HTTP_ERROR,
    SELECTOR_DRIFT,
    BenchmarkError,
    ScoreRow,
    SiteSnapshot,
    get,
    get_json,
)
from news_insight.net.mime import CSV_MIME, HTML_MIME, JAVASCRIPT_MIME, JSON_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "livebench"
TITLE = "LiveBench"
SOURCE_URL = "https://livebench.ai/"
LICENSE = "공개 데이터, 별도 라이선스 표기 없음"
ATTRIBUTION = "LiveBench (Abacus.AI)"
BOARD = "main"
COST_METRIC = "cost_per_success"
MAX_PROBES = 10  # newest dates tried; the bundle lists every release since 2024

_SCRIPT = re.compile(r'<script[^>]+src="([^"]*static/js/main\.[^"]+\.js)"')
# v1 releases are written 2026-01-08, v2 releases 20261025; model version strings look like the
# first, so a date is only a candidate until its table.csv answers
_DATE_DASHED = re.compile(r'"(20\d\d)-(\d\d)-(\d\d)"')
_DATE_COMPACT = re.compile(r'"(20\d\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])"')
# `"claude-opus-5.5":{displayName:"…",organization:"…",openweight:!0,variants:[{…}]}`: a string
# or identifier key, then an object whose only nesting is one array (the variants) of flat objects
_STRING = r'"(?:[^"\\]|\\.)*"'
_BODY = rf'(?:[^{{}}\[\]"]|{_STRING}|\[(?:[^\[\]"]|{_STRING})*\])*'
_MODEL = re.compile(
    rf"(?:(?P<quoted>{_STRING})|(?P<bare>[A-Za-z_$][\w$]*)):\{{(?P<body>{_BODY})\}}"
)
_NESTED = re.compile(rf'\[(?:[^\[\]"]|{_STRING})*\]')
_VARIANT = re.compile(rf"\{{((?:[^{{}}\"]|{_STRING})*)\}}")
_COST_COLUMNS = {
    "questions": "nq_{}",
    "output_tokens": "out_{}",
}
_COST_SHARED = (
    "avg_input_tokens",
    "avg_output_tokens",
    "input_price_per_million",
    "output_price_per_million",
)


def _candidate_dates(script: str, today: date) -> list[date]:
    found: set[date] = set()
    for pattern in (_DATE_DASHED, _DATE_COMPACT):
        for year, month, day in pattern.findall(script):
            try:
                found.add(date(int(year), int(month), int(day)))
            except ValueError:
                continue
    return sorted((d for d in found if d <= today), reverse=True)


def _text(fetcher: SafeFetcher, url: str, mime: frozenset[str]) -> str:
    return get(fetcher, url, mime).content.decode("utf-8", errors="replace")


def _bundle(fetcher: SafeFetcher) -> str:
    home = _text(fetcher, SOURCE_URL, HTML_MIME)
    script = _SCRIPT.search(home)
    if script is None:
        raise BenchmarkError(SELECTOR_DRIFT, "livebench.ai: main script not found")
    return _text(fetcher, urljoin(SOURCE_URL, script.group(1)), JAVASCRIPT_MIME)


def _newest_release(fetcher: SafeFetcher, bundle: str, today: date) -> tuple[date, str]:
    dates = _candidate_dates(bundle, today)
    if not dates:
        raise BenchmarkError(SELECTOR_DRIFT, "livebench.ai: no release dates in the script")
    drifted = False
    for candidate in dates[:MAX_PROBES]:
        try:
            return candidate, _text(fetcher, _data_url(candidate, "table.csv"), CSV_MIME)
        except BenchmarkError as exc:
            if not _absent(exc):
                raise
            drifted = drifted or exc.code == SELECTOR_DRIFT
    # every candidate answered 404 (nothing published) or HTML instead of the CSV (drift)
    raise BenchmarkError(
        SELECTOR_DRIFT if drifted else HTTP_ERROR,
        f"livebench.ai: no table.csv for {dates[:MAX_PROBES]}",
    )


def _absent(exc: BenchmarkError) -> bool:
    """A file that is not there: 404, or the site's HTML fallback page answering for it."""
    return exc.status == 404 or exc.code == SELECTOR_DRIFT


def _data_url(release: date, name: str) -> str:
    return f"{SOURCE_URL}data/{release:%Y%m%d}/{name}"


def _csv_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or reader.fieldnames[0] != "model":
        raise BenchmarkError(SELECTOR_DRIFT, "livebench.ai: CSV has no model column")
    return [row for row in reader if row.get("model")]


def _optional_text(fetcher: SafeFetcher, url: str, mime: frozenset[str]) -> str | None:
    try:
        return _text(fetcher, url, mime)
    except BenchmarkError as exc:
        if _absent(exc):
            return None
        raise


def _unquote(literal: str) -> str:
    try:
        return str(json.loads(literal))
    except ValueError:
        return literal[1:-1]


def _flags(body: str) -> dict[str, Any]:
    """display_name, organization and open_weights of one metadata object's own properties."""
    out: dict[str, Any] = {}
    for key, name in (("displayName", "display_name"), ("organization", "organization")):
        found = re.search(rf"(?:^|,){key}:({_STRING})", body)
        if found:
            out[name] = _unquote(found.group(1))
    weights = re.search(r"(?:^|,)openweight:!([01])(?![\w.])", body)
    if weights:
        out["open_weights"] = weights.group(1) == "0"
    return out


def model_metadata(bundle: str) -> dict[str, dict[str, Any]]:
    """The bundle's per-model metadata (`"id":{displayName:"…",organization:"…",openweight:!0,
    variants:[{rawName:"id-high",…}]}`) as {id: {display_name, organization, open_weights}}.
    open_weights is true only for `openweight:!0`; a model that does not say is closed. A variant
    is a model of its own that inherits its base entry's fields and may override them."""
    found: dict[str, dict[str, Any]] = {}
    for match in _MODEL.finditer(bundle):
        body = _NESTED.sub("", match.group("body"))
        own = _flags(body)
        if "display_name" not in own:  # not a model entry
            continue
        model_id = match.group("quoted")
        key = _unquote(model_id) if model_id else match.group("bare")
        found[key] = {"open_weights": False, **own}
        for variant in _VARIANT.finditer(match.group("body")):
            raw = re.search(rf"(?:^|,)rawName:({_STRING})", variant.group(1))
            if raw:
                found[_unquote(raw.group(1))] = {**found[key], **_flags(variant.group(1))}
    return found


def fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot:
    bundle = _bundle(fetcher)
    release, table_text = _newest_release(fetcher, bundle, now.date())
    categories = get_json(fetcher, _data_url(release, "categories.json"), JSON_MIME)
    if not isinstance(categories, dict):
        raise BenchmarkError(SELECTOR_DRIFT, "livebench.ai: categories.json is not an object")
    cost_text = _optional_text(fetcher, _data_url(release, "cost.csv"), CSV_MIME)
    try:
        breakdown = get_json(fetcher, _data_url(release, "breakdown.json"), JSON_MIME)
    except BenchmarkError as exc:
        if not _absent(exc):
            raise
        breakdown = {}
    breakdown = breakdown if isinstance(breakdown, dict) else {}

    # column → the site's category label ("coding" → "Coding")
    labels = {
        column: label
        for label, columns in categories.items()
        if not label.startswith("_") and isinstance(columns, list)
        for column in columns
    }
    table = _csv_rows(table_text)
    metadata = model_metadata(bundle)
    rows: list[ScoreRow] = []
    for line in table:
        model = line["model"]
        info = metadata.get(model, {})
        for column, text in line.items():
            if column == "model":
                continue
            value = _float(text)
            if value is None:
                continue
            label = labels.get(column)
            extra: dict[str, Any] = {"category": label or column, **info}
            parts = _parts(breakdown, label, model)
            if parts:
                extra["parts"] = parts
            rows.append(
                ScoreRow(
                    board=BOARD,
                    model_raw=model,
                    org=info.get("organization"),
                    config=None,
                    metric=column,
                    value=value,
                    extra=extra,
                )
            )
    cost = _csv_rows(cost_text) if cost_text is not None else []
    rows.extend(_cost_rows(cost, labels, metadata))
    if not rows:
        raise BenchmarkError(SELECTOR_DRIFT, "livebench.ai: table.csv has no scores")
    raw = {
        "release": release.isoformat(),
        "table": table,
        "cost": cost,
        "categories": categories,
        "breakdown": breakdown,
        # the metadata of the table's models: a model turning out open-weight is a change too
        "models": {
            line["model"]: metadata[line["model"]] for line in table if line["model"] in metadata
        },
    }
    return SiteSnapshot(site=SITE, release=release.isoformat(), raw=raw, rows=rows)


def _float(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parts(breakdown: dict[str, Any], label: str | None, model: str) -> dict[str, float]:
    """The site's sub-scores of one category for one model (its expandable row)."""
    models = (breakdown.get(label) or {}).get("models") if label else None
    scores = ((models or {}).get(model) or {}).get("scores")
    return scores if isinstance(scores, dict) else {}


def _cost_rows(
    cost: list[dict[str, str]], labels: dict[str, str], metadata: dict[str, dict[str, Any]]
) -> list[ScoreRow]:
    """Cost per successful task, one row per model and category."""
    rows: list[ScoreRow] = []
    for line in cost:
        shared = {k: v for k in _COST_SHARED if (v := _float(line.get(k))) is not None}
        for column, label in labels.items():
            value = _float(line.get(column))
            if value is None:
                continue
            extra: dict[str, Any] = {"category": label, "column": column, **shared}
            for name, pattern in _COST_COLUMNS.items():
                found = _float(line.get(pattern.format(column)))
                if found is not None:
                    extra[name] = int(found) if found.is_integer() else found
            rows.append(
                ScoreRow(
                    board=BOARD,
                    model_raw=line["model"],
                    org=metadata.get(line["model"], {}).get("organization"),
                    config=None,
                    metric=COST_METRIC,
                    value=value,
                    extra=extra,
                )
            )
    return rows
