"""DeepSWE (Datacurve): pass@1 on 113 software tasks, one row per model + harness + effort.

The v1.1 leaderboard is not served as a file we can rely on (the artifact JSON of the first
version is months old): the homepage embeds each leaderboard it shows in TanStack Router's
stream scripts, as a JavaScript literal (seroval): bare keys, `!0`/`!1`, `$R[n]=` reference
markers. `literal_to_json` turns that literal into JSON; a page that does not parse is drift.
"""

import json
import re
from datetime import datetime
from typing import Any

from news_insight.benchmarks.sources import (
    SELECTOR_DRIFT,
    BenchmarkError,
    ScoreRow,
    SiteSnapshot,
    get,
    number,
)
from news_insight.net.mime import HTML_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "deepswe"
TITLE = "DeepSWE"
SOURCE_URL = "https://deepswe.datacurve.ai/"
LICENSE = "공개 데이터, 별도 라이선스 표기 없음"
ATTRIBUTION = "DeepSWE (Datacurve)"
V1_1 = "v1.1"
V1 = "v1"
_PLOTTED = {"model", "reasoning_effort", "pass_at_1", "ci_lo", "ci_hi"}

_STREAM_SCRIPT = re.compile(r"<script[^>]*data-tsr-stream-part[^>]*>(.*?)</script>", re.S)
_STRING = r'"(?:[^"\\]|\\.)*"'
# a string literal, a bracket, or the key that marks a leaderboard object
_TOKEN = re.compile(rf"{_STRING}|[{{}}\[\]()]|(?<=[{{,])generated_at:")
_PLAIN = re.compile(rf"({_STRING})")
_ESCAPE = re.compile(r"\\(x[0-9a-fA-F]{2}|.)", re.S)
_MARKER = re.compile(r"\$R\[\d+\]=")
_BARE_KEY = re.compile(r"([{,])\s*([A-Za-z_$][\w$]*):")
_NULLS = re.compile(r"\bvoid 0\b|\bundefined\b")
_NOT = re.compile(r"!([01])(?![\w.])")


def _string(match: re.Match[str]) -> str:
    """A JS string escape as JSON: seroval writes `<` as \\x3C, which JSON does not know."""
    code = match.group(1)
    if code.startswith("x") and len(code) == 3:
        return f"\\u00{code[1:]}"
    return "'" if code == "'" else match.group(0)


def _plain(text: str) -> str:
    text = _MARKER.sub("", text)
    text = _NOT.sub(lambda m: "true" if m.group(1) == "0" else "false", text)
    text = _NULLS.sub("null", text)
    return _BARE_KEY.sub(r'\1"\2":', text)


def literal_to_json(text: str) -> Any:
    """Parse a seroval object literal. Only text outside string literals is rewritten, so a
    string holding `$R[1]=`, a colon or a comma comes through as it is."""
    parts = _PLAIN.split(text)
    converted = [
        _ESCAPE.sub(_string, part) if index % 2 else _plain(part)
        for index, part in enumerate(parts)
    ]
    return json.loads("".join(converted))


def _leaderboard_literals(script: str) -> list[str]:
    """The text of every object that has a `generated_at` key (a leaderboard), found by bracket
    matching that skips strings."""
    stack: list[tuple[str, int]] = []
    wanted: set[int] = set()
    found: list[str] = []
    for token in _TOKEN.finditer(script):
        text = token.group()
        if text in ("{", "[", "("):
            stack.append((text, token.start()))
        elif text in ("}", "]", ")"):
            if stack:
                _, start = stack.pop()
                if start in wanted:
                    found.append(script[start : token.end()])
        elif text == "generated_at:" and stack and stack[-1][0] == "{":
            wanted.add(stack[-1][1])
    return found


def _board_name(data: dict[str, Any]) -> str:
    job = data.get("latest_job")
    name = job.get("name") if isinstance(job, dict) else None
    return V1_1 if isinstance(name, str) and "deep-swe-1-1" in name else V1


def _boards(html: str) -> dict[str, dict[str, Any]]:
    scripts = _STREAM_SCRIPT.findall(html)
    if not scripts:
        raise BenchmarkError(SELECTOR_DRIFT, f"{SOURCE_URL}: no router stream scripts")
    boards: dict[str, dict[str, Any]] = {}
    for script in scripts:
        for literal in _leaderboard_literals(script):
            try:
                data = literal_to_json(literal)
            except ValueError as exc:
                raise BenchmarkError(
                    SELECTOR_DRIFT, f"{SOURCE_URL}: leaderboard literal not parseable"
                ) from exc
            if (
                isinstance(data, dict)
                and isinstance(data.get("rows"), list)
                and isinstance(data.get("generated_at"), str)
            ):
                boards.setdefault(_board_name(data), data)
    if not boards:
        raise BenchmarkError(SELECTOR_DRIFT, f"{SOURCE_URL}: no leaderboard in the page")
    return boards


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
    html = get(fetcher, SOURCE_URL, HTML_MIME).content.decode("utf-8", errors="replace")
    boards = _boards(html)
    scores = [
        score
        for board, data in boards.items()
        for row in data["rows"]
        if (score := _score(board, row)) is not None
    ]
    if not scores:
        raise BenchmarkError(SELECTOR_DRIFT, f"{SOURCE_URL}: no usable rows")
    release = max(data["generated_at"][:10] for data in boards.values())
    return SiteSnapshot(site=SITE, release=release, raw={"boards": boards}, rows=scores)
