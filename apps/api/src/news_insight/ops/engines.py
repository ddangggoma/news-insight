"""Card engine health from the recorded card runs (2026-10-08).

Qwen answered 400 on every batch for days (a 6 400-token context) and only the run log said so.
For each engine: when it last produced a batch, and what the latest run said about it; plus how
many of the latest runs produced nothing at all.
"""

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardRun

ENGINES = ("claude", "codex", "agy", "qwen")
LOOKBACK = 300  # runs (about two days at one per 10 minutes)


class EngineHealth(BaseModel):
    name: str
    last_batch_at: datetime | None
    latest_note: str | None  # this engine's part of the latest run's notes


class CardEngineHealth(BaseModel):
    engines: list[EngineHealth]
    zero_runs: int  # latest consecutive runs that made no card and classified nothing
    last_run_at: datetime | None


def card_engine_health(session: Session) -> CardEngineHealth:
    runs = list(
        session.scalars(select(CardRun).order_by(CardRun.started_at.desc()).limit(LOOKBACK))
    )
    zero = 0
    for run in runs:
        if run.ready or run.classified:
            break
        zero += 1
    latest_notes = (runs[0].note or "").split("; ") if runs else []
    engines = []
    for name in ENGINES:
        last = next((run.started_at for run in runs if (run.batches or {}).get(name)), None)
        notes = [note for note in latest_notes if note.startswith(name)]
        engines.append(
            EngineHealth(
                name=name, last_batch_at=last, latest_note=notes[0][:200] if notes else None
            )
        )
    return CardEngineHealth(
        engines=engines, zero_runs=zero, last_run_at=runs[0].started_at if runs else None
    )
