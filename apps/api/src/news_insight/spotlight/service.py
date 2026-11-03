"""The 04:40 spotlight freeze and the Opus write with server-side validation (plan 18 §5).

`freeze` snapshots the candidates once a day. `write` sends them to Claude in one call, keeps only
what passes the checks below and stores an immutable published list. A section the writer left
empty gets the statistical top 10 with the card summaries (`fallback`); when the last attempt of
the day still fails, every section does, so the page is never empty."""

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from news_insight.digest.claude import ClaudeClient, ClaudeError
from news_insight.spotlight.candidates import SECTIONS, collect_candidates
from news_insight.spotlight.models import (
    Spotlight,
    SpotlightEntry,
    SpotlightFreeze,
    SpotlightStatus,
)
from news_insight.spotlight.prompts import (
    INSTRUCTION,
    MAX_HEADLINE,
    MAX_PER_SECTION,
    MAX_RANK_NOTE,
    MAX_SUMMARY,
    MAX_TITLE,
    MAX_WHY_HOT,
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

PAYLOAD_FIELDS = ("cid", "title_ko", "summary_ko", "metrics", "stat_rank")
ERROR_LIMIT = 1000


def freeze(session: Session, *, day: date, now: datetime) -> SpotlightFreeze:
    """Snapshot the day's candidates once; later calls return the same freeze."""
    existing = session.scalars(
        select(SpotlightFreeze).where(SpotlightFreeze.spotlight_date == day)
    ).one_or_none()
    if existing is not None:
        return existing
    found = collect_candidates(session, day=day, now=now)
    snapshot = SpotlightFreeze(
        spotlight_date=day,
        frozen_at=now,
        candidates={
            section: [candidate.to_json() for candidate in found.get(section, [])]
            for section in SECTIONS
        },
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def build_payload(
    snapshot: SpotlightFreeze,
    previous: dict[str, list[str]],
    benchmarks: dict[str, Any] | None,
) -> dict[str, Any]:
    """What Claude reads (§5.2): the candidates with short ids, yesterday's titles, benchmark
    changes. Urls and real item ids stay on the server."""
    return {
        "date": snapshot.spotlight_date.isoformat(),
        "sections": {
            section: [
                {field: candidate[field] for field in PAYLOAD_FIELDS}
                for candidate in snapshot.candidates.get(section, [])
            ]
            for section in SECTIONS
        },
        "previous": previous,
        "benchmarks": benchmarks or {"changes": [], "new_models": []},
    }


def previous_titles(session: Session, day: date) -> dict[str, list[str]]:
    """Titles of the previous calendar day's published spotlight, by section in rank order."""
    rows = session.execute(
        select(SpotlightEntry.section, SpotlightEntry.title_ko)
        .join(Spotlight, Spotlight.id == SpotlightEntry.spotlight_id)
        .where(
            Spotlight.spotlight_date == day - timedelta(days=1),
            Spotlight.status == SpotlightStatus.PUBLISHED,
        )
        .order_by(SpotlightEntry.section, SpotlightEntry.rank)
    )
    titles: dict[str, list[str]] = {}
    for section, title in rows:
        titles.setdefault(section, []).append(title)
    return titles


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) else None


def _product_key(name: str) -> str:
    return "product:" + "-".join(name.casefold().split())


def _merged_metrics(members: list[dict[str, Any]]) -> dict[str, Any]:
    """Numbers add up across a product group; any other value is the first member's."""
    merged: dict[str, Any] = {}
    for member in members:
        for name, value in member["metrics"].items():
            if name not in merged:
                merged[name] = value
            elif all(
                isinstance(v, int | float) and not isinstance(v, bool)
                for v in (merged[name], value)
            ):
                merged[name] += value
    return merged


def _entry(
    section: str,
    members: list[dict[str, Any]],
    *,
    title_ko: str,
    product_name: str | None,
    summary: str,
    why_hot: str,
    rank_note: str | None,
    fallback: bool,
) -> dict[str, Any]:
    grouped = len(members) > 1
    item_ids = list(dict.fromkeys(i for member in members for i in member["item_ids"]))
    metrics = _merged_metrics(members) | ({"group_size": len(members)} if grouped else {})
    return {
        "section": section,
        "cids": [member["cid"] for member in members],
        "key": _product_key(product_name) if product_name else members[0]["key"],
        "item_ids": item_ids,
        "title_ko": title_ko,
        "product_name": product_name,
        "summary": summary,
        "why_hot": why_hot,
        "rank_note": rank_note,
        "metrics": metrics,
        "stat_rank": min(member["stat_rank"] for member in members),
        "fallback": fallback,
    }


def _checked(
    section: str, raw: Any, by_cid: dict[str, dict[str, Any]]
) -> tuple[int, list[dict[str, Any]], dict[str, Any]] | None:
    """One writer entry if its fields pass: (writer rank, member candidates, entry fields)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("cids"), list):
        return None
    members: list[dict[str, Any]] = []
    for cid in raw["cids"]:
        # an unknown or other-section cid makes the whole entry untrustworthy
        if not isinstance(cid, str) or cid not in by_cid:
            return None
        members.append(by_cid[cid])
    if not members:
        return None
    summary, why_hot = _text(raw.get("summary")), _text(raw.get("why_hot"))
    title = _text(raw.get("title_ko")) or members[0]["title_ko"]
    note = raw.get("rank_note")
    if note is not None and not isinstance(note, str):
        return None
    note = (note or "").strip() or None
    if not summary or why_hot is None:
        return None
    if (
        len(summary) > MAX_SUMMARY
        or len(why_hot) > MAX_WHY_HOT
        or len(title) > MAX_TITLE
        or (note is not None and len(note) > MAX_RANK_NOTE)
    ):
        return None
    rank = raw.get("rank")
    order = rank if isinstance(rank, int) and not isinstance(rank, bool) else MAX_PER_SECTION * 100
    product_name = None
    if section == "product":
        product_name = _text(raw.get("product_name")) or None
    else:
        members = members[:1]  # only a product can be a group
    fields = {
        "title_ko": title,
        "product_name": product_name,
        "summary": summary,
        "why_hot": why_hot,
        "rank_note": note,
    }
    return order, members, fields


def validate(
    output: dict[str, Any], candidates: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    """The writer's entries that pass the checks of §5.5, per section, ranked 1..n.

    Dropped: unknown or other-section cids, an over-long field, a cid already used by an earlier
    entry (a group keeps its other cids), a product named twice, and everything past the tenth.
    Sections the writer did not return come back empty."""
    sections = output.get("sections")
    sections = sections if isinstance(sections, dict) else {}
    result: dict[str, list[dict[str, Any]]] = {}
    for section in SECTIONS:
        by_cid = {c["cid"]: c for c in candidates.get(section, [])}
        raw_entries = sections.get(section)
        if not isinstance(raw_entries, list):
            raw_entries = []
        checked = [
            found for raw in raw_entries if (found := _checked(section, raw, by_cid)) is not None
        ]
        checked.sort(key=lambda found: found[0])  # stable: ties keep the writer's order
        used: set[str] = set()
        keys: set[str] = set()
        kept: list[dict[str, Any]] = []
        for _, members, fields in checked:
            members = [m for m in members if m["cid"] not in used]
            if not members:
                continue
            built = _entry(section, members, fallback=False, **fields)
            if built["key"] in keys:
                continue
            used.update(m["cid"] for m in members)
            keys.add(built["key"])
            kept.append(built)
            if len(kept) == MAX_PER_SECTION:
                break
        for rank, built in enumerate(kept, start=1):
            built["rank"] = rank
        result[section] = kept
    return result


def fallback_entries(section: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The statistical top 10 with the card summaries."""
    top = sorted(candidates, key=lambda c: c["stat_rank"])[:MAX_PER_SECTION]
    built = []
    for rank, candidate in enumerate(top, start=1):
        row = _entry(
            section,
            [candidate],
            title_ko=candidate["title_ko"],
            product_name=None,
            summary=candidate["summary_ko"],
            why_hot="",
            rank_note=None,
            fallback=True,
        )
        row["rank"] = rank
        built.append(row)
    return built


def _row(session: Session, day: date) -> Spotlight | None:
    return session.scalars(select(Spotlight).where(Spotlight.spotlight_date == day)).one_or_none()


def _store(
    session: Session,
    row: Spotlight | None,
    snapshot: SpotlightFreeze,
    *,
    status: SpotlightStatus,
    model: str,
    cost_usd: float | None,
    headline: str,
    benchmark_note: str,
    error: str | None,
    now: datetime,
) -> Spotlight:
    """Create the day's row, or update the FAILED one of an earlier attempt in place."""
    if row is None:
        row = Spotlight(spotlight_date=snapshot.spotlight_date, freeze_id=snapshot.id)
        session.add(row)
    row.freeze_id = snapshot.id
    row.status = status
    row.model = model
    row.cost_usd = cost_usd
    row.headline = headline
    row.benchmark_note = benchmark_note
    row.error = error[:ERROR_LIMIT] if error else None
    row.generated_at = now
    session.flush()
    return row


def _publish(
    session: Session,
    row: Spotlight | None,
    snapshot: SpotlightFreeze,
    chosen: dict[str, list[dict[str, Any]]],
    **fields: Any,
) -> Spotlight:
    published = _store(session, row, snapshot, status=SpotlightStatus.PUBLISHED, **fields)
    session.execute(delete(SpotlightEntry).where(SpotlightEntry.spotlight_id == published.id))
    for section in SECTIONS:
        for built in chosen.get(section, []):
            session.add(
                SpotlightEntry(
                    spotlight_id=published.id,
                    section=section,
                    rank=built["rank"],
                    stat_rank=built["stat_rank"],
                    key=built["key"],
                    item_ids=built["item_ids"],
                    title_ko=built["title_ko"],
                    product_name=built["product_name"],
                    summary=built["summary"],
                    why_hot=built["why_hot"],
                    rank_note=built["rank_note"],
                    metrics=built["metrics"],
                    fallback=built["fallback"],
                )
            )
    session.flush()
    return published


def write(
    session: Session,
    *,
    day: date,
    now: datetime,
    client: ClaudeClient,
    model: str,
    final_attempt: bool,
    benchmarks: dict[str, Any] | None = None,
) -> Spotlight:
    """Publish the day's spotlight once. A published day is returned untouched; a failed attempt
    is recorded (and raised, for the next scheduled try) unless it is the last of the day, which
    publishes the statistical lists instead."""
    row = _row(session, day)
    if row is not None and row.status is SpotlightStatus.PUBLISHED:
        return row
    snapshot = freeze(session, day=day, now=now)
    payload = build_payload(snapshot, previous_titles(session, day), benchmarks)
    try:
        result = client.generate(
            payload,
            schema=OUTPUT_SCHEMA,
            model=model,
            system=SYSTEM_PROMPT,
            instruction=INSTRUCTION,
        )
        if not isinstance(result.structured.get("sections"), dict):
            raise ClaudeError("the response has no sections")
    except ClaudeError as exc:
        if not final_attempt:
            _store(
                session,
                row,
                snapshot,
                status=SpotlightStatus.FAILED,
                model=model,
                cost_usd=None,
                headline="",
                benchmark_note="",
                error=str(exc),
                now=now,
            )
            raise
        logger.warning("spotlight writer failed on the last attempt; publishing fallback: %s", exc)
        everything = {
            section: fallback_entries(section, snapshot.candidates.get(section, []))
            for section in SECTIONS
        }
        return _publish(
            session,
            row,
            snapshot,
            everything,
            model=model,
            cost_usd=None,
            headline="",
            benchmark_note="",
            error=str(exc),
            now=now,
        )
    chosen = validate(result.structured, snapshot.candidates)
    for section in SECTIONS:
        if not chosen[section]:
            chosen[section] = fallback_entries(section, snapshot.candidates.get(section, []))
    structured = result.structured
    return _publish(
        session,
        row,
        snapshot,
        chosen,
        model=result.model,
        cost_usd=result.cost_usd,
        headline=(_text(structured.get("headline")) or "")[:MAX_HEADLINE],
        benchmark_note=_text(structured.get("benchmark_note")) or "",
        error=None,
        now=now,
    )
