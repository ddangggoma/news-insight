"""The 04:40 spotlight freeze and the Opus write with server-side validation (plan 18 §5).

`freeze` snapshots the candidates once a day: per section the 최근 24시간 ones (group "now")
and the 지속 주목 ones (group "sustained", B3). `write` sends them to Claude in one call, keeps
only what passes the checks below and stores an immutable published list: up to 10 now and 5
sustained entries per section, a short group lending its places to the other (15 in all).
Places the writer left open are filled from the statistical order with the card summaries
(`fallback`); when the last attempt of the day still fails, every section is, so the page is
never empty. The server adds each entry's signal tags and technology field."""

import logging
from datetime import date, datetime, timedelta
from typing import Any, TypeGuard

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.digest.claude import ClaudeClient, ClaudeError
from news_insight.spotlight.candidates import AI_FIELD, MIN_OSS, SECTIONS, collect_candidates
from news_insight.spotlight.models import (
    Spotlight,
    SpotlightEntry,
    SpotlightFreeze,
    SpotlightGroup,
    SpotlightStatus,
)
from news_insight.spotlight.prompts import (
    INSTRUCTION,
    MAX_BENCHMARK_NOTE,
    MAX_HEADLINE,
    MAX_NOW,
    MAX_PRODUCT_NAME,
    MAX_RANK_NOTE,
    MAX_SUMMARY,
    MAX_SUSTAINED,
    MAX_TAG,
    MAX_TAGS,
    MAX_TITLE,
    MAX_TOTAL,
    MAX_WHY_HOT,
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
)
from news_insight.spotlight.sustained import collect_sustained

logger = logging.getLogger(__name__)

PAYLOAD_FIELDS = ("cid", "title_ko", "summary_ko", "metrics", "stat_rank")
ERROR_LIMIT = 1000
NOW, SUSTAINED = SpotlightGroup.NOW.value, SpotlightGroup.SUSTAINED.value
GROUPS = (NOW, SUSTAINED)


def group_of(candidate: dict[str, Any]) -> str:
    """A candidate's group; freezes from before B3 have only 24 h ones."""
    return SUSTAINED if candidate.get("group") == SUSTAINED else NOW


def _of_group(candidates: list[dict[str, Any]], group: str) -> list[dict[str, Any]]:
    return [candidate for candidate in candidates if group_of(candidate) == group]


def freeze(session: Session, *, day: date, now: datetime) -> SpotlightFreeze:
    """Snapshot the day's candidates once; later calls return the same freeze. A failure of
    the 지속 주목 collection leaves the day with its 24 h candidates only."""
    existing = session.scalars(
        select(SpotlightFreeze).where(SpotlightFreeze.spotlight_date == day)
    ).one_or_none()
    if existing is not None:
        return existing
    found = collect_candidates(session, day=day, now=now)
    sustained: dict[str, list[Any]] = {}
    try:
        with session.begin_nested():
            sustained = dict(collect_sustained(session, day=day))
    except Exception:  # noqa: BLE001 - the day still has its 24 h lists
        logger.exception("spotlight: sustained candidates unavailable; freezing the 24 h ones")
    snapshot = SpotlightFreeze(
        spotlight_date=day,
        frozen_at=now,
        candidates={
            section: [
                candidate.to_json()
                for candidate in [*found.get(section, []), *sustained.get(section, [])]
            ]
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
    """What Claude reads (§5.2): per section the 24 h and the sustained candidates with short
    ids, yesterday's titles, benchmark changes. Urls and real item ids stay on the server."""
    return {
        "date": snapshot.spotlight_date.isoformat(),
        "sections": {
            section: {
                group: [
                    {field: candidate[field] for field in PAYLOAD_FIELDS}
                    for candidate in _of_group(snapshot.candidates.get(section, []), group)
                ]
                for group in GROUPS
            }
            for section in SECTIONS
        },
        "previous": previous,
        "benchmarks": benchmarks or {"changes": [], "new_models": []},
    }


def previous_titles(session: Session, day: date) -> dict[str, list[str]]:
    """Titles of the previous calendar day's published spotlight, by section: the 24 h entries
    in rank order, then the sustained ones."""
    rows = session.execute(
        select(SpotlightEntry.section, SpotlightEntry.title_ko)
        .join(Spotlight, Spotlight.id == SpotlightEntry.spotlight_id)
        .where(
            Spotlight.spotlight_date == day - timedelta(days=1),
            Spotlight.status == SpotlightStatus.PUBLISHED,
        )
        .order_by(SpotlightEntry.section, SpotlightEntry.group != NOW, SpotlightEntry.rank)
    )
    titles: dict[str, list[str]] = {}
    for section, title in rows:
        titles.setdefault(section, []).append(title)
    return titles


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) else None


# sections whose writer may group candidates under one product (or model, service) name
GROUPED = frozenset({"product", "ai"})
# metrics that are places or day counts: a group keeps the best, never a sum
_BEST_LOW = frozenset({"rank", "trend_rank", "best_rank"})
_BEST_HIGH = frozenset({"days_active", "listed_days"})


def _product_key(name: str, section: str = "product") -> str:
    # casefold can expand a name; the column holds 200 characters
    return (f"{section}:" + "-".join(name.casefold().split()))[:200]


def _number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _merged_metrics(members: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts add up across a product group, places and day counts keep the best, the first
    day seen the earliest; any other value is the first member's."""
    merged: dict[str, Any] = {}
    for member in members:
        for name, value in member["metrics"].items():
            if name not in merged:
                merged[name] = value
            elif name == "first_seen" and isinstance(value, str):
                merged[name] = min(str(merged[name]), value)
            elif not (_number(merged[name]) and _number(value)) or name == "from":
                continue
            elif name in _BEST_LOW:
                merged[name] = min(merged[name], value)
            elif name in _BEST_HIGH:
                merged[name] = max(merged[name], value)
            else:
                merged[name] += value
    return merged


def signals(section: str, metrics: dict[str, Any]) -> list[str]:
    """Deterministic, reader-facing reasons an entry is listed, from its numbers alone."""
    out: list[str] = []

    def count(name: str) -> int:
        value = metrics.get(name)
        return int(value) if _number(value) else 0

    if count("source_count") >= 5:
        out.append(f"보도 {count('source_count')}곳")
    if max(count("community_mentions"), count("mentions") if section != "oss" else 0) >= 3:
        out.append("커뮤니티 확산")
    if count("days_active") >= 3:
        out.append(f"7일 중 {count('days_active')}일")
    basis, trend, best = metrics.get("basis"), count("trend_rank"), count("best_rank")
    if basis == "github_daily" and trend:
        out.append(f"GitHub {trend}위")
    elif basis == "github_weekly" and trend:
        out.append(f"GitHub 주간 {trend}위")
    elif basis in ("github_daily", "github_weekly") and best:
        out.append(f"GitHub 최고 {best}위")
    elif basis == "hf_trending":
        out.append("HF 트렌딩")
    elif basis == "benchmark" and count("rank"):
        out.append(f"벤치마크 {count('rank')}위")
    if count("upvotes") >= 20:
        out.append(f"추천 {count('upvotes')}")
    return out


def _tags(raw: Any) -> list[str]:
    """Opus's insight tags that pass: short non-empty strings, each once, the first three."""
    if not isinstance(raw, list):
        return []
    kept: list[str] = []
    for tag in raw:
        text = " ".join(tag.split()) if isinstance(tag, str) else ""
        if text and len(text) <= MAX_TAG and text not in kept:
            kept.append(text)
    return kept[:MAX_TAGS]


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
    tags: list[str] | None = None,
) -> dict[str, Any]:
    grouped = len(members) > 1
    item_ids = list(dict.fromkeys(i for member in members for i in member["item_ids"]))
    metrics = _merged_metrics(members) | ({"group_size": len(members)} if grouped else {})
    return {
        "section": section,
        "group": group_of(members[0]),
        "cids": [member["cid"] for member in members],
        "key": _product_key(product_name, section) if product_name else members[0]["key"],
        "item_ids": item_ids,
        "title_ko": title_ko,
        "product_name": product_name,
        "summary": summary,
        "why_hot": why_hot,
        "rank_note": rank_note,
        "metrics": metrics,
        "stat_rank": min(member["stat_rank"] for member in members),
        "fallback": fallback,
        "tags": tags or [],
        "signals": signals(section, metrics),
    }


def _checked(
    section: str, raw: Any, by_cid: dict[str, dict[str, Any]]
) -> tuple[int, list[dict[str, Any]], dict[str, Any]] | None:
    """One writer entry if its fields pass: (writer rank, member candidates, entry fields)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("cids"), list):
        return None
    members: list[dict[str, Any]] = []
    for cid in raw["cids"]:
        # an unknown, other-section or other-group cid makes the whole entry untrustworthy
        if not isinstance(cid, str) or cid not in by_cid:
            return None
        if by_cid[cid] not in members:  # a cid repeated inside one entry counts once
            members.append(by_cid[cid])
    if not members:
        return None
    summary, why_hot = _text(raw.get("summary")), _text(raw.get("why_hot"))
    title = _text(raw.get("title_ko")) or members[0]["title_ko"]
    note = raw.get("rank_note")  # "" (or an absent field) means the order follows stat_rank
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
    order = rank if isinstance(rank, int) and not isinstance(rank, bool) else MAX_TOTAL * 100
    product_name = None
    if section in GROUPED:
        product_name = _text(raw.get("product_name")) or None
        if product_name is not None and len(product_name) > MAX_PRODUCT_NAME:
            return None  # the key built from it must fit its column
    else:
        members = members[:1]  # only a product (or an AI model or service) can be a group
    fields = {
        "title_ko": title,
        "product_name": product_name,
        "summary": summary,
        "why_hot": why_hot,
        "rank_note": note,
        "tags": _tags(raw.get("tags")),
    }
    return order, members, fields


def _raw_groups(output: dict[str, Any], section: str) -> dict[str, Any]:
    sections = output.get("sections")
    listed = sections.get(section) if isinstance(sections, dict) else None
    return listed if isinstance(listed, dict) else {}


def listed_counts(output: dict[str, Any]) -> dict[str, dict[str, int | None]]:
    """How many entries the writer listed per section and group; None when the key is missing
    or is not a list. Empty lists in both groups are the writer's decision that nothing
    qualifies, which `write` respects."""
    counts: dict[str, dict[str, int | None]] = {}
    for section in SECTIONS:
        groups = _raw_groups(output, section)
        counts[section] = {
            group: len(listed) if isinstance(listed := groups.get(group), list) else None
            for group in GROUPS
        }
    return counts


def _overlaps(built: dict[str, Any], others: list[dict[str, Any]]) -> bool:
    """The same key, or an item in common, as one of `others`."""
    items = set(built["item_ids"])
    return any(built["key"] == other["key"] or items & set(other["item_ids"]) for other in others)


def quotas(now: int, sustained: int) -> tuple[int, int]:
    """How many of each group a section keeps: 10 now and 5 sustained, a short group lending
    its places to the other up to 15 in all."""
    keep_sustained = min(sustained, MAX_SUSTAINED)
    keep_now = min(now, MAX_TOTAL - keep_sustained)
    return keep_now, min(sustained, MAX_TOTAL - keep_now)


def _valid_group(
    section: str, raw_entries: Any, by_cid: dict[str, dict[str, Any]], taken: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A group's writer entries that pass, in the writer's order, none repeating `taken`."""
    if not isinstance(raw_entries, list):
        raw_entries = []
    checked = [
        found for raw in raw_entries if (found := _checked(section, raw, by_cid)) is not None
    ]
    checked.sort(key=lambda found: found[0])  # stable: ties keep the writer's order
    used: set[str] = set()
    kept: list[dict[str, Any]] = []
    for _, members, fields in checked:
        members = [m for m in members if m["cid"] not in used]
        if not members:
            continue
        built = _entry(section, members, fallback=False, **fields)
        if _overlaps(built, kept) or _overlaps(built, taken):
            continue
        used.update(m["cid"] for m in members)
        kept.append(built)
        if len(kept) == MAX_TOTAL:
            break
    return kept


def _ranked(now: list[dict[str, Any]], sustained: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for group in (now, sustained):
        for rank, built in enumerate(group, start=1):
            built["rank"] = rank
    return [*now, *sustained]


def validate(
    output: dict[str, Any], candidates: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    """The writer's entries that pass the checks of §5.5, per section: the 24 h group then the
    sustained one, each ranked 1..n.

    Dropped: unknown, other-section or other-group cids, an over-long field, a cid already used
    by an earlier entry (a group keeps its other cids), a product named twice, a sustained entry
    repeating a 24 h one (same key or an item in common), and everything past the quotas.
    Sections the writer did not return come back empty."""
    result: dict[str, list[dict[str, Any]]] = {}
    for section in SECTIONS:
        raw = _raw_groups(output, section)
        found = candidates.get(section, [])
        now = _valid_group(section, raw.get(NOW), {c["cid"]: c for c in _of_group(found, NOW)}, [])
        sustained = _valid_group(
            section,
            raw.get(SUSTAINED),
            {c["cid"]: c for c in _of_group(found, SUSTAINED)},
            now,
        )
        keep_now, keep_sustained = quotas(len(now), len(sustained))
        result[section] = _ranked(now[:keep_now], sustained[:keep_sustained])
    return result


def _fallback_row(section: str, candidate: dict[str, Any]) -> dict[str, Any]:
    return _entry(
        section,
        [candidate],
        title_ko=candidate["title_ko"],
        product_name=None,
        summary=candidate["summary_ko"],
        why_hot="",
        rank_note=None,
        fallback=True,
    )


def _fill(
    section: str,
    kept: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    target: int,
    taken: list[dict[str, Any]],
) -> None:
    """Append to `kept` the best unused candidates by stat_rank (card text, fallback) until it
    holds `target`; none repeats `kept` or `taken`."""
    used = {cid for built in kept for cid in built["cids"]}
    for candidate in sorted(candidates, key=lambda c: c["stat_rank"]):
        if len(kept) >= target:
            return
        if candidate["cid"] in used:
            continue
        row = _fallback_row(section, candidate)
        if _overlaps(row, kept) or _overlaps(row, taken):
            continue
        kept.append(row)


def top_up(
    section: str, kept: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A section filled toward 15 from the statistical order: the 24 h group to 10, the
    sustained one to 5 (never past 15 with what the other group already holds, e.g. 13 places
    the writer lent to 24 h), then either one past its share while the other is short. The
    open-source list reaches MIN_OSS whenever its candidates allow (B1)."""
    now = [built for built in kept if built["group"] == NOW]
    sustained = [built for built in kept if built["group"] == SUSTAINED]
    now_found, sustained_found = _of_group(candidates, NOW), _of_group(candidates, SUSTAINED)

    def share(group: list[dict[str, Any]], quota: int, other: list[dict[str, Any]]) -> int:
        return max(len(group), min(quota, MAX_TOTAL - len(other)))

    _fill(section, now, now_found, share(now, MAX_NOW, sustained), sustained)
    _fill(section, sustained, sustained_found, share(sustained, MAX_SUSTAINED, now), now)
    _fill(section, now, now_found, MAX_TOTAL - len(sustained), sustained)
    _fill(section, sustained, sustained_found, MAX_TOTAL - len(now), now)
    if section == "oss" and len(now) + len(sustained) < MIN_OSS:
        _fill(section, now, now_found, MIN_OSS - len(sustained), sustained)
    return _ranked(now, sustained)


def fallback_entries(section: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The statistical lists with the card summaries: the top 10 of the 24 h group and the
    top 5 of the sustained one (a short group lending its places to the other)."""
    return top_up(section, [], candidates)


def _fields(session: Session, chosen: dict[str, list[dict[str, Any]]]) -> dict[int, str]:
    """The technology field of each lead item's ready card."""
    leads = {
        built["item_ids"][0] for rows in chosen.values() for built in rows if built["item_ids"]
    }
    if not leads:
        return {}
    return {
        item_id: field
        for item_id, field in session.execute(
            select(ItemCard.item_id, ItemCard.field).where(
                ItemCard.item_id.in_(leads),
                ItemCard.status == CardStatus.READY,
                ItemCard.field.is_not(None),
            )
        )
    }


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
    technology = _fields(session, chosen)
    for section in SECTIONS:
        for built in chosen.get(section, []):
            lead = built["item_ids"][0] if built["item_ids"] else None
            # a leaderboard model has no item; it is an AI model all the same
            field = technology.get(lead) if lead is not None else None
            if field is None and lead is None and section == "ai":
                field = AI_FIELD
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
                    group=built["group"],
                    tags=built["tags"],
                    signals=built["signals"],
                    field=field,
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
    listed = listed_counts(result.structured)
    for section in SECTIONS:
        # empty lists in both groups are the writer's "nothing qualifies" (real interviews
        # only, products only); otherwise the statistical order fills the places left open.
        # The open-source list is always filled (B1: at least ten when ten exist).
        declined = all(count == 0 for count in listed[section].values())
        if declined and section != "oss":
            continue
        chosen[section] = top_up(section, chosen[section], snapshot.candidates.get(section, []))
    structured = result.structured
    return _publish(
        session,
        row,
        snapshot,
        chosen,
        model=result.model,
        cost_usd=result.cost_usd,
        headline=(_text(structured.get("headline")) or "")[:MAX_HEADLINE],
        benchmark_note=(_text(structured.get("benchmark_note")) or "")[:MAX_BENCHMARK_NOTE],
        error=None,
        now=now,
    )
