"""One module per leaderboard site; each `fetch(fetcher, now)` returns a SiteSnapshot.

The site's own spelling is kept (`model_raw`, `config`) and every field its charts and tables
need beyond the plotted value goes to `extra`; matching names to AiModel is the service's job.
A page that is not the JSON/CSV we expect (a login wall, a moved file) is `selector_drift`, so
the last good snapshot stays in place.

A module that sets `USES_PREVIOUS = True` takes the raw payload of its site's latest snapshot as
`fetch(fetcher, now, previous)` (None on a first run or a dry run): it can send a conditional
request (an ETag) or reuse unchanged parts, and raises NotModified when nothing changed. A
module that validates a schema strictly raises `parse_error` when the site's shape changes.
"""

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from news_insight.collect.contracts import CollectorError
from news_insight.collect.http import fetch_checked
from news_insight.net.safe_fetch import FetchResponse, SafeFetcher

SELECTOR_DRIFT = "selector_drift"
HTTP_ERROR = "http_error"
CONFIG_ERROR = "config_error"
PARSE_ERROR = "parse_error"

_TRAILING_PARENS = re.compile(r"\(([^()]*)\)\s*$")


class BenchmarkError(Exception):
    """A site could not be read. `code`: selector_drift, http_error or config_error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


class NotModified(Exception):
    """The site says nothing changed since the previous snapshot (an ETag answered 304, or a
    commit SHA is the one already stored): the collector keeps that snapshot and marks it seen."""


@dataclass
class ScoreRow:
    board: str
    model_raw: str
    org: str | None
    config: str | None
    metric: str
    value: float
    ci_low: float | None = None
    ci_high: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SiteSnapshot:
    site: str
    release: str
    raw: dict[str, Any]
    rows: list[ScoreRow]


def get(
    fetcher: SafeFetcher,
    url: str,
    allowed_mime: frozenset[str],
    *,
    headers: dict[str, str] | None = None,
    max_bytes: int | None = None,
    not_modified: bool = False,
) -> FetchResponse:
    """A 200 response of one of `allowed_mime`; anything else is a BenchmarkError.
    `not_modified`: a 304 (the answer to a conditional request) is returned as well."""
    try:
        response = fetch_checked(
            fetcher, url, allowed_mime=allowed_mime, headers=headers, max_bytes=max_bytes
        )
    except CollectorError as exc:
        if exc.code == "blocked_mime":
            raise BenchmarkError(SELECTOR_DRIFT, f"{url}: {exc}") from exc
        raise BenchmarkError(
            HTTP_ERROR, f"{url}: {exc}", status=exc.status_code, retryable=exc.retryable
        ) from exc
    if response.status_code == 304 and not_modified:
        return response
    if response.status_code != 200:
        raise BenchmarkError(HTTP_ERROR, f"HTTP {response.status_code} from {url}")
    return response


def get_json(
    fetcher: SafeFetcher,
    url: str,
    allowed_mime: frozenset[str],
    *,
    headers: dict[str, str] | None = None,
) -> Any:
    response = get(fetcher, url, allowed_mime, headers=headers)
    try:
        return json.loads(response.content)
    except ValueError as exc:
        raise BenchmarkError(SELECTOR_DRIFT, f"{url}: not JSON") from exc


def number(value: Any) -> float | None:
    """A JSON/CSV value as a float; booleans, nulls, text and NaN/infinity are not scores."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def config_from_name(name: str) -> str | None:
    """ "Gemini 4 Carbon (High)" → "High": the effort level a site writes in parentheses."""
    found = _TRAILING_PARENS.search(name)
    return found.group(1).strip() or None if found else None
