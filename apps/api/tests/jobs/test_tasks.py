from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import pytest

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
