"""Daily radar signal snapshots (checklist PRD-1).

At the 04:40 freeze the radar cards of this week (compared up to the same point, STAT-2) and of
last week are stored for the briefing date. The digest and the strategy roles get them as
evidence, and the published briefing lists them with links to the radar.
"""

from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from news_insight.public import radar as radar_queries
from news_insight.public.companies import COMPANY_TONES, company_radar
from news_insight.public.filters import ReaderFilters
from news_insight.public.periods import calendar_window, current_key
from news_insight.public.signals import TONES
from news_insight.signals.models import RadarSignalSnapshot

TONE_LABEL = {
    "surge": "급상승",
    "event": "이례적인 날",
    "new": "신규 기술",
    "back": "재등장",
    "early": "연구 선행",
    "pull": "개발자 반응 선행",
    "shift": "상용화 이동",
    "hype": "화제 과열",
    "thin": "검증 필요",
    "gap": "국내 공백",
    "link": "융합 신호",
    "cool": "관심 감소",
    "company_surge": "기업 급부상",
    "company_shift": "기업 활동 전환",
    "theme_entry": "기업 새 테마 진입",
    "new_entrant": "신흥 업체",
}
PERIOD = "week"


def snapshot(session: Session, *, day: date, now: datetime) -> list[RadarSignalSnapshot]:
    """Compute and store the day's cards (replacing any earlier snapshot of that day)."""
    session.execute(delete(RadarSignalSnapshot).where(RadarSignalSnapshot.snapshot_date == day))
    current = calendar_window(PERIOD, current_key(PERIOD, now))
    filters = ReaderFilters.build(scope="relevant", q=None)
    rows: list[RadarSignalSnapshot] = []
    for window in (current, current.previous()):
        body = radar_queries.radar(session, filters, window, current.key, now)
        companies = company_radar(session, filters, window, current.key, now)
        for signal in [*body.signals, *companies.signals]:
            rows.append(
                RadarSignalSnapshot(
                    snapshot_date=day,
                    period=PERIOD,
                    window_key=window.key,
                    is_current=window.key == current.key,
                    tone=signal.tone,
                    focus_kind=signal.focus.kind,
                    focus_key=signal.focus.key,
                    title=signal.title,
                    detail=signal.detail,
                    score=signal.score,
                    created_at=now,
                )
            )
    session.add_all(rows)
    session.flush()
    return rows


def for_day(session: Session, day: date) -> list[RadarSignalSnapshot]:
    """The day's cards: this week first, then last week's cards on topics not already shown."""
    rows = list(
        session.scalars(select(RadarSignalSnapshot).where(RadarSignalSnapshot.snapshot_date == day))
    )
    order = {tone: i for i, tone in enumerate((*TONES, *COMPANY_TONES))}
    rows.sort(key=lambda r: (not r.is_current, order.get(r.tone, 99)))
    seen: set[tuple[str, str]] = set()
    picked = []
    for row in rows:
        focus = (row.focus_kind, row.focus_key)
        if focus not in seen:
            seen.add(focus)
            picked.append(row)
    return picked


def ensure(session: Session, *, day: date, now: datetime) -> list[RadarSignalSnapshot]:
    if not session.scalar(
        select(RadarSignalSnapshot.id).where(RadarSignalSnapshot.snapshot_date == day).limit(1)
    ):
        snapshot(session, day=day, now=now)
    return for_day(session, day)


def radar_path(row: RadarSignalSnapshot) -> str:
    if row.focus_kind == "search":  # a company name the registry does not know yet
        return f"/?q={quote(row.focus_key)}"
    return f"/radar/{row.period}/{row.window_key}?focus={row.focus_kind}:{row.focus_key}"


def evidence(rows: list[RadarSignalSnapshot]) -> list[dict[str, Any]]:
    """Prompt payload: what the radar's statistics flagged, as context for the articles."""
    return [
        {
            "signal": TONE_LABEL.get(row.tone, row.tone),
            "window": row.window_key + (" (진행 중)" if row.is_current else ""),
            "topic": row.title,
            "detail": row.detail,
        }
        for row in rows
    ]
