"""EPO Open Patent Services (OPS 3.2): published patent documents by CQL search (plan 16 #5).

Free registration at developers.epo.org gives a consumer key and secret, kept in .env as
SOURCE_SECRET_EPO_OPS_KEY / SOURCE_SECRET_EPO_OPS_SECRET; without them the source fails
validation and never collects. Each run takes an OAuth client-credentials token (cached until
shortly before it expires) and asks for the newest bibliographic records of `config.cql`, e.g.
`pn=CN and cpc=H01M and pd>={today-30d}` — `{today-Nd}` becomes yyyymmdd. OPS covers the
DOCDB offices, so one adapter serves EP and CN (and others) publications alike.
"""

import base64
import json
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from news_insight.collect.contracts import CollectContext, CollectorError, CollectResult, RawItem
from news_insight.net.mime import JSON_MIME
from news_insight.net.safe_fetch import FetchError, FetchResponse, SafeFetcher
from news_insight.secrets import SecretError, secret_value
from news_insight.sources.models import Source

AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"
SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
KEY, SECRET = "EPO_OPS_KEY", "EPO_OPS_SECRET"
DATE_MACRO = re.compile(r"\{today(?:-(\d{1,4})d)?\}")
_tokens: dict[str, tuple[str, float]] = {}  # consumer key -> (token, monotonic expiry)


def _credentials() -> tuple[str, str]:
    try:
        return secret_value(KEY), secret_value(SECRET)
    except SecretError as exc:
        raise CollectorError("config_error", str(exc), retryable=False) from exc


def _token(fetcher: SafeFetcher) -> str:
    key, secret = _credentials()
    cached = _tokens.get(key)
    if cached and cached[1] > time.monotonic():
        return cached[0]
    basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
    try:
        response = fetcher.fetch(
            AUTH_URL,
            allowed_mime=JSON_MIME,
            headers={"Authorization": f"Basic {basic}"},
            form={"grant_type": "client_credentials"},
        )
    except FetchError as exc:
        raise CollectorError(
            exc.code, f"EPO OPS token request failed: {exc}", retryable=True
        ) from exc
    if response.status_code != 200:
        raise CollectorError(
            "auth_failed",
            f"EPO OPS token request answered HTTP {response.status_code}",
            retryable=False,
        )
    payload = json.loads(response.content)
    token = str(payload["access_token"])
    lifetime = int(payload.get("expires_in") or 1199)
    _tokens[key] = (token, time.monotonic() + max(60, lifetime - 60))
    return token


def search_url(config: dict[str, Any], now: datetime) -> str:
    today = now.astimezone(UTC).date()

    def date(match: re.Match[str]) -> str:
        return (today - timedelta(days=int(match.group(1) or 0))).strftime("%Y%m%d")

    cql = DATE_MACRO.sub(date, str(config.get("cql") or ""))
    if not cql:
        raise CollectorError("config_error", "EPO OPS source needs config.cql", retryable=False)
    size = max(1, min(100, int(config.get("range", 50))))
    return f"{SEARCH_URL}?q={quote(cql)}&Range=1-{size}"


def _fetch(fetcher: SafeFetcher, url: str) -> FetchResponse:
    try:
        return fetcher.fetch(
            url,
            allowed_mime=JSON_MIME,
            headers={"Authorization": f"Bearer {_token(fetcher)}", "Accept": "application/json"},
        )
    except FetchError as exc:
        raise CollectorError(exc.code, str(exc), retryable=True) from exc


def probe(source: Source, fetcher: SafeFetcher, now: datetime) -> FetchResponse:
    """V2 for OPS: a real token and a one-record search (the endpoint alone answers 4xx)."""
    return _fetch(fetcher, search_url({**source.config, "range": 1}, now))


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("$")
    text = " ".join(str(value).split()) if value is not None else ""
    return text or None


def _title(biblio: dict[str, Any]) -> str | None:
    titles = _list(biblio.get("invention-title"))
    english = [t for t in titles if isinstance(t, dict) and t.get("@lang") == "en"]
    for title in (*english, *titles):
        if text := _text(title):
            return text
    return None


def _applicants(biblio: dict[str, Any]) -> list[str]:
    names: list[str] = []
    applicants = (biblio.get("parties") or {}).get("applicants") or {}
    for applicant in _list(applicants.get("applicant")):
        if applicant.get("@data-format") not in (None, "epodoc", "original"):
            continue
        name = _text((applicant.get("applicant-name") or {}).get("name"))
        if name:  # epodoc names end in the country: "CATL [CN]"
            name = re.sub(r"\s*\[[A-Z]{2}\]$", "", name).rstrip(" ,;")
            if name and name not in names:
                names.append(name)
    return names[:5]


def _published(biblio: dict[str, Any]) -> datetime | None:
    reference = biblio.get("publication-reference") or {}
    for document in _list(reference.get("document-id")):
        raw = _text(document.get("date"))
        if raw and re.fullmatch(r"\d{8}", raw):
            return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=UTC)
    return None


def _abstract(document: dict[str, Any]) -> str | None:
    abstracts = _list(document.get("abstract"))
    chosen = next(
        (a for a in abstracts if a.get("@lang") == "en"), abstracts[0] if abstracts else None
    )
    if not chosen:
        return None
    parts = [t for p in _list(chosen.get("p")) if (t := _text(p))]
    return " ".join(parts)[:2000] or None


def to_items(payload: dict[str, Any]) -> list[RawItem]:
    result = ((payload.get("ops:world-patent-data") or {}).get("ops:biblio-search") or {}).get(
        "ops:search-result"
    ) or {}
    items: list[RawItem] = []
    for entry in _list(result.get("exchange-documents")):
        document = entry.get("exchange-document") or {}
        number = "".join(
            str(document.get(part, "")) for part in ("@country", "@doc-number", "@kind")
        )
        biblio = document.get("bibliographic-data") or {}
        title = _title(biblio)
        if not number or not title:
            continue
        applicants = _applicants(biblio)
        items.append(
            RawItem(
                stable_id=number,
                url=f"https://worldwide.espacenet.com/patent/search?q=pn%3D{number}",
                title=title,
                published_at=_published(biblio),
                author="; ".join(applicants) or None,
                summary=_abstract(document),
            )
        )
    return items


def collect_ops(fetcher: SafeFetcher, context: CollectContext) -> CollectResult:
    response = _fetch(fetcher, search_url(context.config, context.now))
    if response.status_code == 404:  # OPS answers 404 when nothing matches
        return CollectResult(items=[], status_code=404, elapsed_ms=response.elapsed_ms)
    if response.status_code != 200:
        raise CollectorError(
            "http_error",
            f"EPO OPS search answered HTTP {response.status_code}",
            retryable=response.status_code >= 500 or response.status_code == 429,
        )
    try:
        payload = json.loads(response.content)
    except ValueError as exc:
        raise CollectorError("parse_error", "EPO OPS answer is not JSON", retryable=False) from exc
    items = to_items(payload)
    return CollectResult(
        items=items[: context.item_limit], status_code=200, elapsed_ms=response.elapsed_ms
    )
