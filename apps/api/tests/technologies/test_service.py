import pytest
from sqlalchemy.orm import Session

from news_insight.technologies import service

pytestmark = pytest.mark.db


def test_labels_are_looked_up_in_chunks(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 2026-10-05: one IN list per call passed PostgreSQL's 65,535 bind parameters
    monkeypatch.setattr(service, "LABEL_CHUNK", 2)
    keys = [f"tech-{n}" for n in range(5)]
    assert service.labels_for(db_session, keys) == {key: key for key in keys}
