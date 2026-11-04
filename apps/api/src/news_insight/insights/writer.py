"""The daily Opus insight of the 연구 and 특허 menus (plan 19 §3), written after the spotlight.

`build_input` reads the last 7 days against the average of the 4 weeks before, with the same
stats queries and gates as the reader views (public/domains.py): changes by field, theme,
company and country or office (15 each at most), the rising fields (only when the history
reaches back far enough), the watched companies, and up to five representative documents per
field. The coverage notes tell the writer which axes not to read as trends (a short history,
an OpenAlex enrichment backlog), and the axes the reader views suppress are left out.

`write` sends it to Claude in one call and keeps what passes `validate`: doc_ids from the input
only, one line per known field and company, sentences of 200 characters at most, quantities
(건, %, 배 ...) that the input holds; at least two overview sentences or the attempt fails.
A published day is immutable; a failed attempt is stored and overwritten by the next digest
run's."""

import logging
import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.digest.claude import ClaudeClient, ClaudeError
from news_insight.insights.models import DomainInsightRecord, InsightKind, InsightStatus
from news_insight.insights.prompts import (
    INSTRUCTION,
    MAX_COMPANIES,
    MAX_DOC_IDS,
    MAX_OVERVIEW,
    MAX_TEXT,
    MIN_OVERVIEW,
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
)
from news_insight.public import domains
from news_insight.public.domains import Doc, Span
from news_insight.public.periods import KST
from news_insight.taxonomy.catalog import FIELD_KEYS, FIELDS

logger = logging.getLogger(__name__)

WEEK = 7
BASELINE_WEEKS = 4
TOP = 15
CANDIDATES = 30  # companies and regions considered for the top changes
DOCS_PER_FIELD = 5
SUMMARY_MAX = 200
ERROR_LIMIT = 1000
NOTE_SHORT = "직전 4주의 집계가 일부 없어 급증 분야를 판단하지 않음. 증감을 추세로 말하지 말 것"
NOTE_ENRICHMENT = (
    "과거 기간의 OpenAlex 기관·국가 보강률이 낮아 국가별 변화는 넣지 않음."
    " 기업·기관 증감도 보강 진행의 영향일 수 있으니 추세로 말하지 말 것"
)
NOTE_RESEARCH = "기업·기관·국가는 OpenAlex 보강이 끝난 논문 기준(최근 7일 보강률 {current}%)"
# a quantity in a sentence: a number with one of these units must be one of the input's numbers
QUANTITY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(건|%|퍼센트|배|편|곳|개사|개)")


class InsightError(Exception):
    """The writer's output failed the checks, or there was nothing to write about."""


def _domain(kind: str) -> domains.Domain:
    from news_insight.public.patents import PatentDomain
    from news_insight.public.research import ResearchDomain

    return ResearchDomain() if kind == InsightKind.RESEARCH else PatentDomain()


# ---------------------------------------------------------------- input


def _change(label_key: str, label: str, counts: list[int]) -> dict[str, Any]:
    """{key, label, count, baseline, change_pct, ratio} from [4 baseline weeks..., this week]."""
    current, past = counts[-1], counts[:-1]
    baseline = round(sum(past) / len(past), 1) if past else 0.0
    return {
        "key": label_key,
        "label": label,
        "count": current,
        "baseline": baseline,
        "change_pct": round((current - baseline) / baseline * 100) if baseline else None,
        "ratio": round(current / baseline, 1) if baseline else None,
    }


def _moved(rows: Iterable[dict[str, Any]], limit: int = TOP) -> list[dict[str, Any]]:
    """The biggest movers first (absolute change against the baseline), then the busiest."""
    present = [r for r in rows if r["count"] or r["baseline"]]
    present.sort(key=lambda r: (-abs(r["count"] - r["baseline"]), -r["count"], r["key"]))
    return present[:limit]


def _short(text: str | None) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= SUMMARY_MAX else text[: SUMMARY_MAX - 1] + "…"


def _doc(doc: Doc) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if doc.publication_number is not None or doc.patent_source is not None:
        for name in ("publication_number", "office", "press"):
            value = getattr(doc, name)
            if value:
                metrics[name] = value
        if doc.applicants:
            metrics["applicants"] = doc.applicants[:3]
    else:
        for name in ("venue", "cited_by", "cited_growth", "mentions", "upvotes"):
            value = getattr(doc, name)
            if value:
                metrics[name] = value
    return {
        "doc_id": doc.id,
        "field": doc.field,
        "title": doc.title_ko or doc.title,
        "summary": _short(doc.summary),
        "date": doc.occurred_at.astimezone(KST).date().isoformat(),
        "companies": [c.label for c in doc.companies],
        "orgs": doc.orgs,
        "watched": doc.watched,
        "metrics": metrics,
    }


def input_as_of(session: Session, day: date) -> tuple[date, domains.StatsRange]:
    """The last day the input counts: the day before `day`, or the last built if earlier."""
    built = domains.stats_range(session)
    yesterday = day - timedelta(days=1)
    return (min(yesterday, built.last) if built.last else yesterday), built


def build_input(
    session: Session, kind: str, *, day: date
) -> tuple[dict[str, Any], set[int], set[str]]:
    """(the writer's JSON, the doc ids it may cite, the company keys it may name)."""
    domain = _domain(kind)
    end, built = input_as_of(session, day)
    windows = domains.spans(end, WEEK, BASELINE_WEEKS + 1)
    ctx = domains.Context(
        session=session,
        domain=domain,
        query=domains.Query(
            tab="overview",
            period="week",
            field=None,
            company=None,
            org=None,
            kind="company",
            page=1,
        ),
        as_of=end,
        days=WEEK,
        window=windows[-1],
        previous=windows[-2],
        trend=windows,
        watched=domains.watched_keys(session),
        built=built,
    )
    model = domain.model
    zero = [0] * len(windows)
    history_ok = ctx.history_ok(windows)
    enrichment_ok = not domain.enrichment_regions or ctx.enrichment_ok(windows)
    notes: list[str] = []
    if not history_ok:
        notes.append(NOTE_SHORT)
    if not enrichment_ok:
        notes.append(NOTE_ENRICHMENT)

    by_field = domains._field_counts(ctx, windows)
    fields = [_change(f.key, f.name, by_field.get(f.key, zero)) for f in FIELDS]
    total = _change("total", "전체", domains._sum(by_field, len(windows)))
    rising = []
    for f in FIELDS if history_ok else ():
        flag, z, mean = domains.flag_of(by_field.get(f.key, zero), BASELINE_WEEKS)
        if flag == "rise":
            rising.append({"key": f.key, "label": f.name, "z": z})

    themes: list[dict[str, Any]] = []
    for f in FIELDS:
        counts = domain.themes(session, f.key, windows)
        themes.extend(_change(t.key, t.name, counts.get(t.key, zero)) for t in f.themes)

    baseline_span = Span(start=windows[0].start, end=windows[-2].end)
    keys = list(
        dict.fromkeys(
            [
                *domains.top_keys(
                    session, model, "company", ctx.window, model.company_key, CANDIDATES
                ),
                *domains.top_keys(
                    session, model, "company", baseline_span, model.company_key, CANDIDATES
                ),
            ]
        )
    )
    refs = domains.company_refs(session, keys)
    per_company = domains._company_counts(ctx, windows, list(refs))
    companies = _moved(
        _change(key, ref.label, domains._sum(per_company.get(key, {}), len(windows)))
        | {"watched": ref.watched}
        for key, ref in refs.items()
    )

    regions: list[dict[str, Any]] = []
    if enrichment_ok:
        per_region = domains.bucketed(
            session, model, domain.region_dim, windows, [domain.region_column()]
        )
        regions = _moved(
            _change(key, domain.region_label(key), counts)
            for (key,), counts in per_region.items()
            if key
        )

    watched_refs = domains.company_refs(session, ctx.watched)
    per_watched = domains._company_counts(ctx, windows, list(watched_refs))
    watched = []
    for key, ref in watched_refs.items():
        per_field = per_watched.get(key, {})
        row = _change(key, ref.label, domains._sum(per_field, len(windows)))
        if row["count"] or row["baseline"]:
            top = sorted(
                ((n[-1], k) for k, n in per_field.items() if n[-1]), key=lambda p: (-p[0], p[1])
            )
            watched.append(
                row
                | {
                    "relation": ref.relation,
                    "fields": [domains.field_label(k) for _, k in top[:3]],
                }
            )
    watched.sort(key=lambda r: (-r["count"], -r["baseline"], r["key"]))

    documents: list[dict[str, Any]] = []
    for f in FIELDS:
        _, docs = ctx.docs(size=DOCS_PER_FIELD, field=f.key)
        documents.extend(_doc(doc) for doc in docs)

    if kind == InsightKind.RESEARCH:
        days = ctx._days or []
        current = [r for r in days if ctx.window.start <= r[0] <= ctx.window.end]
        docs_n = sum(r[1] for r in current)
        share = round(sum(r[2] for r in current) / docs_n * 100) if docs_n else 0
        notes.append(NOTE_RESEARCH.format(current=share))
    else:
        coverage = domain.coverage(session, ctx.window)
        if coverage is not None:
            notes.append(coverage.note)

    payload = {
        "kind": kind,
        "date": day.isoformat(),
        "as_of": end.isoformat(),
        "window": {"start": ctx.window.start.isoformat(), "end": ctx.window.end.isoformat()},
        "baseline_window": {
            "start": baseline_span.start.isoformat(),
            "end": baseline_span.end.isoformat(),
        },
        "total": total,
        "fields": fields,
        "themes": _moved(themes),
        "companies": companies,
        "regions_axis": domain.region_dim,
        "regions": regions,
        "rising_fields": rising,
        "watched": watched,
        "documents": documents,
        "coverage_notes": notes,
    }
    known_companies = {row["key"] for row in companies} | {row["key"] for row in watched}
    return payload, {doc["doc_id"] for doc in documents}, known_companies


# ---------------------------------------------------------------- validation


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _normal(number: str) -> str:
    """A number as a sentence may write it, normalised: 1,234 → 1234, 2.0 → 2, 03 → 3."""
    return _fmt(float(number.replace(",", "")))


def _numbers(value: Any, out: set[str]) -> set[str]:
    """Every number of the input, normalised, with each fraction also rounded to a whole."""
    if isinstance(value, bool):
        return out
    if isinstance(value, int | float):
        out.add(_fmt(value))
        out.add(_fmt(round(value)))
    elif isinstance(value, str):
        out.update(_normal(m) for m in re.findall(r"\d[\d,]*(?:\.\d+)?", value))
    elif isinstance(value, dict):
        for item in value.values():
            _numbers(item, out)
    elif isinstance(value, list):
        for item in value:
            _numbers(item, out)
    return out


def _text(raw: Any, numbers: set[str]) -> str | None:
    """A sentence that passes: non-empty, 200 characters at most, quantities from the input."""
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.split())
    if not text or len(text) > MAX_TEXT:
        return None
    if any(_normal(m.group(1)) not in numbers for m in QUANTITY.finditer(text)):
        return None
    return text


def _doc_ids(raw: Any, known: set[int]) -> list[int]:
    ids = (
        [i for i in raw if isinstance(i, int) and not isinstance(i, bool) and i in known]
        if (isinstance(raw, list))
        else []
    )
    return list(dict.fromkeys(ids))[:MAX_DOC_IDS]


def _entries(raw: Any) -> list[dict[str, Any]]:
    return [entry for entry in raw if isinstance(entry, dict)] if isinstance(raw, list) else []


def validate(
    output: dict[str, Any],
    *,
    doc_ids: set[int],
    company_keys: set[str],
    numbers: set[str],
) -> dict[str, Any]:
    """The output that passes. Unknown doc_ids are dropped from a sentence; a sentence is
    dropped when its text is empty, over 200 characters or quotes a quantity the input does not
    hold, and a field or company line when its key is unknown or repeated. Fewer than two
    overview sentences left raise InsightError."""
    overview = []
    for entry in _entries(output.get("overview")):
        text = _text(entry.get("text"), numbers)
        if text is not None:
            overview.append({"text": text, "doc_ids": _doc_ids(entry.get("doc_ids"), doc_ids)})
    overview = overview[:MAX_OVERVIEW]
    if len(overview) < MIN_OVERVIEW:
        raise InsightError(f"only {len(overview)} valid overview sentences")
    fields: dict[str, dict[str, Any]] = {}
    for entry in _entries(output.get("fields")):
        field, text = entry.get("field"), _text(entry.get("text"), numbers)
        if isinstance(field, str) and field in FIELD_KEYS and field not in fields and text:
            fields[field] = {
                "field": field,
                "text": text,
                "doc_ids": _doc_ids(entry.get("doc_ids"), doc_ids),
            }
    companies: dict[str, dict[str, Any]] = {}
    for entry in _entries(output.get("companies")):
        key, text = entry.get("company_key"), _text(entry.get("text"), numbers)
        if isinstance(key, str) and key in company_keys and key not in companies and text:
            companies[key] = {
                "company_key": key,
                "text": text,
                "doc_ids": _doc_ids(entry.get("doc_ids"), doc_ids),
            }
    watch = _text(output.get("watch"), numbers) or ""
    order = {f.key: i for i, f in enumerate(FIELDS)}
    return {
        "overview": overview,
        "fields": sorted(fields.values(), key=lambda e: order[e["field"]]),
        "companies": list(companies.values())[:MAX_COMPANIES],
        "watch": watch,
    }


# ---------------------------------------------------------------- write


def existing(session: Session, kind: str, day: date) -> DomainInsightRecord | None:
    return session.scalars(
        select(DomainInsightRecord).where(
            DomainInsightRecord.insight_date == day,
            DomainInsightRecord.kind == InsightKind(kind),
        )
    ).one_or_none()


def _store(
    session: Session,
    row: DomainInsightRecord | None,
    *,
    kind: str,
    day: date,
    status: InsightStatus,
    model: str,
    cost_usd: float | None,
    payload: dict[str, Any],
    error: str | None,
    now: datetime,
) -> DomainInsightRecord:
    """Create the day's row, or overwrite the FAILED one of an earlier attempt in place."""
    if row is None:
        row = DomainInsightRecord(insight_date=day, kind=InsightKind(kind))
        session.add(row)
    row.status = status
    row.model = model
    row.cost_usd = cost_usd
    row.payload = payload
    row.error = error[:ERROR_LIMIT] if error else None
    row.generated_at = now
    session.flush()
    return row


def write(
    session: Session,
    kind: str,
    day: date | None = None,
    *,
    client: ClaudeClient,
    model: str,
    now: datetime | None = None,
) -> DomainInsightRecord:
    """Publish the kind's insight for `day` (today, KST, by default) once. A published row is
    returned untouched; a failed attempt (the CLI, the checks, nothing to write about) is stored
    as FAILED and returned, for the next digest run to try again."""
    now = now or datetime.now(UTC)
    day = day or now.astimezone(KST).date()
    row = existing(session, kind, day)
    if row is not None and row.status is InsightStatus.PUBLISHED:
        return row
    payload, doc_ids, company_keys = build_input(session, kind, day=day)
    base = {"as_of": payload["as_of"]}
    try:
        if not doc_ids:
            raise InsightError("no documents in the last 7 days")
        result = client.generate(
            payload,
            schema=OUTPUT_SCHEMA,
            model=model,
            system=SYSTEM_PROMPT,
            instruction=INSTRUCTION,
        )
        checked = validate(
            result.structured,
            doc_ids=doc_ids,
            company_keys=company_keys,
            numbers=_numbers(payload, set()),
        )
    except (ClaudeError, InsightError) as exc:
        logger.warning("insights: %s insight for %s not written: %s", kind, day, exc)
        return _store(
            session,
            row,
            kind=kind,
            day=day,
            status=InsightStatus.FAILED,
            model=model,
            cost_usd=None,
            payload=base,
            error=str(exc),
            now=now,
        )
    return _store(
        session,
        row,
        kind=kind,
        day=day,
        status=InsightStatus.PUBLISHED,
        model=result.model,
        cost_usd=result.cost_usd,
        payload=base | checked,
        error=None,
        now=now,
    )
