from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from news_insight.jobs import tasks


def test_dispatch_due_enqueues_each_claimed_source(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[object]:
        yield object()

    def claim(session: object, now: datetime) -> list[int]:
        return [3, 7]

    queued: list[int] = []
    monkeypatch.setattr(tasks, "session_scope", scope)
    monkeypatch.setattr(tasks, "claim_due_sources", claim)
    monkeypatch.setattr(tasks.collect_source_task, "delay", queued.append)

    assert tasks.dispatch_due() == 2
    assert queued == [3, 7]


@pytest.mark.db
@pytest.mark.parametrize("spotlight_fails", [False, True])
def test_briefing_freeze_also_freezes_the_spotlight(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, spotlight_fails: bool
) -> None:
    from sqlalchemy import select

    from news_insight.briefing.models import BriefingFreeze
    from news_insight.spotlight import service
    from news_insight.spotlight.candidates import SECTIONS
    from news_insight.spotlight.models import SpotlightFreeze

    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session

    order: list[str] = []
    real_commit = db_session.commit

    def commit() -> None:
        order.append("commit")
        real_commit()

    def collect(session: Session, *, day: date, now: datetime) -> dict[str, list[object]]:
        order.append("spotlight")
        if spotlight_fails:
            raise RuntimeError("boom")
        return {section: [] for section in SECTIONS}

    monkeypatch.setattr(tasks, "session_scope", scope)
    monkeypatch.setattr(service, "collect_candidates", collect)
    monkeypatch.setattr(db_session, "commit", commit)

    tasks.briefing_freeze_task()

    # the briefing freeze is committed before the spotlight step starts
    assert order[:2] == ["commit", "spotlight"]
    # a failed spotlight freeze must not take the briefing freeze with it
    assert db_session.scalars(select(BriefingFreeze)).one() is not None
    assert len(db_session.scalars(select(SpotlightFreeze)).all()) == (0 if spotlight_fails else 1)
