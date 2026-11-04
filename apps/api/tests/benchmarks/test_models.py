from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import AiModel, BenchmarkScore, BenchmarkSnapshot

pytestmark = pytest.mark.db
FETCHED = datetime(2026, 11, 3, 3, 0, tzinfo=UTC)


def _snapshot(session: Session, site: str = "livebench", sha: str = "a" * 64) -> BenchmarkSnapshot:
    snap = BenchmarkSnapshot(
        site=site, release="2026-10-01", fetched_at=FETCHED, sha256=sha, raw={"rows": 1}
    )
    session.add(snap)
    session.flush()
    return snap


def test_snapshot_is_unique_per_site_and_hash(db_session: Session) -> None:
    _snapshot(db_session)
    _snapshot(db_session, site="lmarena")  # same bytes on another site are fine
    with pytest.raises(IntegrityError), db_session.begin_nested():
        _snapshot(db_session)


def test_scores_cascade_with_snapshot(db_session: Session) -> None:
    snap = _snapshot(db_session)
    model = AiModel(name="claude-opus-5-5", org="Anthropic", open_weights=False)
    db_session.add(model)
    db_session.flush()
    db_session.add_all(
        [
            BenchmarkScore(
                snapshot_id=snap.id,
                site="livebench",
                board="overall",
                model_raw="Claude Opus 5.5",
                model_id=model.id,
                metric="score",
                value=71.5,
                ci_low=70.1,
                ci_high=72.9,
            ),
            BenchmarkScore(
                snapshot_id=snap.id,
                site="livebench",
                board="overall",
                model_raw="Mystery 1",
                metric="score",
                value=40.0,
            ),
        ]
    )
    db_session.flush()
    rows = db_session.scalars(select(BenchmarkScore).order_by(BenchmarkScore.id)).all()
    assert rows[0].extra == {} and rows[1].model_id is None
    db_session.delete(snap)
    db_session.flush()
    db_session.expire_all()
    assert db_session.scalars(select(BenchmarkScore)).all() == []
