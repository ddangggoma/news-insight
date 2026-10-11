"""Card processing progress for the console (2026-10-11): where every collected item stands,
what each engine produced per day and hour, engine quotas and recent runs.

Item states, in this order: `ready` (a card for the current content), `archive` (published more
than 30 days before collection: never carded), `held` (paused or retired source: not carded),
`failed` (three attempts on the current content), `repeat` (waits for the card of the earlier
item it repeats), `capped` (a non-active source over its 24-hour card cap) and `pending`.
"""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from news_insight.cards.service import CAP_BYPASS_DX, MAX_ATTEMPTS
from news_insight.config import get_settings
from news_insight.console.schemas import CardRunOut

KST = ZoneInfo("Asia/Seoul")
DIMENSIONS = ("status", "track", "category", "region", "language")
STATES = ("ready", "pending", "capped", "repeat", "failed", "held", "archive")


class ProgressDay(BaseModel):
    date: str  # KST, YYYY-MM-DD
    inflow: int  # items first seen that day
    failed: int  # cards that failed that day
    cards: dict[str, int]  # ready cards generated that day, by engine group


class ProgressHour(BaseModel):
    hour: str  # KST, YYYY-MM-DDTHH
    cards: dict[str, int]


class ProgressRow(BaseModel):
    key: str
    total: int
    ready: int
    pending: int
    capped: int
    repeat: int
    failed: int
    held: int
    archive: int


class EngineQuota(BaseModel):
    engine: str
    weekly: int | None
    five_hour: int | None
    seen_at: datetime


class CardProgress(BaseModel):
    generated_at: datetime
    totals: dict[str, int]
    repeats_by_kind: dict[str, int]
    days: list[ProgressDay]
    hours: list[ProgressHour]
    breakdown: dict[str, list[ProgressRow]]
    quotas: list[EngineQuota]
    runs: list[CardRunOut]


# one row per item with its state and the dimensions the console groups by
_STATES = """
create temp table progress_items on commit drop as
with busy as (
  select i.source_id
  from items i
  join item_cards c on c.item_id = i.id
  join sources s on s.id = i.source_id
  where s.status <> 'active' and c.generated_at >= now() - interval '24 hours'
  group by i.source_id
  having count(*) >= :cap
)
select
  s.status::text as status, s.track::text as track, s.category, s.region::text as region,
  s.language,
  case
    when c.status = 'ready' and c.input_hash = i.content_hash then 'ready'
    when not (i.published_at is null or i.published_at >= i.first_seen_at - interval '30 days')
      then 'archive'
    when s.status in ('paused', 'retired') then 'held'
    when c.status = 'failed' and c.input_hash = i.content_hash and c.attempts >= :attempts
      then 'failed'
    when d.duplicate_of is not null then 'repeat'
    when s.status <> 'active' and i.source_id in (select source_id from busy)
      and coalesce(t.dx_probability, 0) < :bypass then 'capped'
    else 'pending'
  end as state
from items i
join sources s on s.id = i.source_id
left join item_cards c on c.item_id = i.id
left join item_triage t on t.item_id = i.id
left join item_dedup d on d.item_id = i.id
"""

_GROUP = "case when engine like 'agy%' then 'agy' else coalesce(engine, 'unknown') end"


def _engine_group(engine: str | None) -> str:
    if engine and engine.startswith("agy"):
        return "agy"
    return engine or "unknown"


def card_progress(session: Session, *, now: datetime, days: int = 14) -> CardProgress:
    settings = get_settings()
    session.execute(text("drop table if exists pg_temp.progress_items"))
    session.execute(
        text(_STATES),
        {
            "cap": settings.card_unvalidated_daily_cap or 10**9,
            "attempts": MAX_ATTEMPTS,
            "bypass": settings.card_cap_bypass_dx or CAP_BYPASS_DX,
        },
    )
    totals: dict[str, int] = dict.fromkeys(STATES, 0)
    for state, count in session.execute(
        text("select state, count(*) from progress_items group by state")
    ).tuples():
        totals[state] = count
    totals["items"] = sum(totals[state] for state in STATES)

    breakdown: dict[str, list[ProgressRow]] = {}
    for dimension in DIMENSIONS:
        rows = session.execute(
            text(
                f"select coalesce({dimension}, '-') as key, state, count(*) "  # noqa: S608
                f"from progress_items group by 1, 2"
            )
        ).tuples()
        by_key: dict[str, dict[str, int]] = {}
        for key, state, count in rows:
            by_key.setdefault(key, dict.fromkeys(STATES, 0))[state] = count
        breakdown[dimension] = sorted(
            (
                ProgressRow(key=key, total=sum(counts.values()), **counts)
                for key, counts in by_key.items()
            ),
            key=lambda row: row.total,
            reverse=True,
        )

    start = (now.astimezone(KST) - timedelta(days=days - 1)).date()
    inflow = dict(
        session.execute(
            text(
                "select to_char(first_seen_at at time zone 'Asia/Seoul', 'YYYY-MM-DD'), count(*) "
                "from items where first_seen_at >= :start group by 1"
            ),
            {"start": datetime.combine(start, datetime.min.time(), tzinfo=KST)},
        )
        .tuples()
        .all()
    )
    day_cards: dict[str, dict[str, int]] = {}
    day_failed: dict[str, int] = {}
    for day, engine, status, count in session.execute(
        text(
            "select to_char(generated_at at time zone 'Asia/Seoul', 'YYYY-MM-DD'), engine, "
            "status::text, count(*) from item_cards where generated_at >= :start group by 1, 2, 3"
        ),
        {"start": datetime.combine(start, datetime.min.time(), tzinfo=KST)},
    ).tuples():
        if status == "ready":
            bucket = day_cards.setdefault(day, {})
            group = _engine_group(engine)
            bucket[group] = bucket.get(group, 0) + count
        else:
            day_failed[day] = day_failed.get(day, 0) + count
    day_list = [
        ProgressDay(
            date=(key := (start + timedelta(days=n)).isoformat()),
            inflow=inflow.get(key, 0),
            failed=day_failed.get(key, 0),
            cards=day_cards.get(key, {}),
        )
        for n in range(days)
    ]

    hour_start = (now - timedelta(hours=47)).replace(minute=0, second=0, microsecond=0)
    hour_cards: dict[str, dict[str, int]] = {}
    for hour, group, count in session.execute(
        text(
            "select to_char(generated_at at time zone 'Asia/Seoul', 'YYYY-MM-DD\"T\"HH24'), "
            f"{_GROUP}, count(*) from item_cards "
            "where status = 'ready' and generated_at >= :start group by 1, 2"
        ),
        {"start": hour_start},
    ).tuples():
        hour_cards.setdefault(hour, {})[group] = count
    hours = []
    for n in range(48):
        moment = (hour_start + timedelta(hours=n)).astimezone(KST)
        key = moment.strftime("%Y-%m-%dT%H")
        hours.append(ProgressHour(hour=key, cards=hour_cards.get(key, {})))

    repeats = dict(
        session.execute(
            text(
                "select matched_by, count(*) from item_dedup "
                "where duplicate_of is not null group by 1"
            )
        )
        .tuples()
        .all()
    )
    totals["copied"] = sum(repeats.values())

    quotas: dict[str, EngineQuota] = {}
    for started, quota in session.execute(
        text(
            "select started_at, quota from card_runs "
            "where started_at >= now() - interval '3 days' and quota ? 'engine' "
            "order by started_at desc"
        )
    ).tuples():
        engine = str(quota.get("engine"))
        if engine not in quotas:
            quotas[engine] = EngineQuota(
                engine=engine,
                weekly=_int(quota.get("weekly")),
                five_hour=_int(quota.get("five_hour")),
                seen_at=started,
            )

    runs = [
        CardRunOut(
            started_at=row.started_at,
            finished_at=row.finished_at,
            ready=row.ready,
            failed=row.failed,
            batches=row.batches or {},
            quota=row.quota or {},
            note=row.note,
        )
        for row in session.execute(
            text(
                "select started_at, finished_at, ready, failed, batches, quota, note "
                "from card_runs order by id desc limit 30"
            )
        )
    ]
    return CardProgress(
        generated_at=now,
        totals=totals,
        repeats_by_kind=repeats,
        days=day_list,
        hours=hours,
        breakdown=breakdown,
        quotas=sorted(quotas.values(), key=lambda q: q.engine),
        runs=runs,
    )


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
