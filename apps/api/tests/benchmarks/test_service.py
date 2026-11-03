from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import AiModel, BenchmarkScore, BenchmarkSnapshot
from news_insight.benchmarks.service import collect_all
from news_insight.benchmarks.sources import artificial_analysis, deepswe, lmarena
from news_insight.ops.checks import check_benchmarks, run_checks
from news_insight.ops.models import Severity
from tests.benchmarks.fakes import (
    FakeClock,
    Router,
    all_sites,
    artificial_analysis_routes,
    deepswe_routes,
    livebench_routes,
    lmarena_routes,
    reply,
)

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 3, 3, 30, tzinfo=UTC)
KEY = "SOURCE_SECRET_ARTIFICIAL_ANALYSIS_KEY"


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY, "test-key")
    clock = FakeClock()
    monkeypatch.setattr(lmarena, "_clock", clock.monotonic)
    monkeypatch.setattr(lmarena, "_sleep", clock.sleep)


def snapshots(session: Session) -> dict[str, int]:
    return dict(
        session.execute(
            select(BenchmarkSnapshot.site, func.count()).group_by(BenchmarkSnapshot.site)
        )
        .tuples()
        .all()
    )


def score_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(BenchmarkScore)) or 0


def test_collect_all_saves_every_site_and_links_names(db_session: Session) -> None:
    carbon = AiModel(name="gemini-4-carbon", org="Google")
    db_session.add(carbon)
    db_session.flush()
    result = collect_all(db_session, all_sites().fetcher(), NOW)
    assert result == {
        "deepswe": "saved",
        "livebench": "saved",
        "lmarena": "saved",
        "artificial_analysis": "saved",
    }
    assert snapshots(db_session) == {
        "deepswe": 1,
        "livebench": 1,
        "lmarena": 1,
        "artificial_analysis": 1,
    }
    snap = db_session.scalars(
        select(BenchmarkSnapshot).where(BenchmarkSnapshot.site == "livebench")
    ).one()
    assert snap.release == "2026-10-25" and snap.fetched_at == NOW and len(snap.sha256) == 64
    linked = db_session.scalars(
        select(BenchmarkScore).where(
            BenchmarkScore.site == "lmarena", BenchmarkScore.model_raw == "Gemini 4 Carbon (High)"
        )
    ).all()
    assert linked and {s.model_id for s in linked} == {carbon.id}
    assert {s.config for s in linked} == {"High"}
    unmatched = db_session.scalars(
        select(BenchmarkScore).where(BenchmarkScore.model_raw == "gpt-5-5")
    ).first()
    assert unmatched is not None and unmatched.model_id is None
    assert (
        unmatched.snapshot_id
        == db_session.scalars(
            select(BenchmarkSnapshot.id).where(BenchmarkSnapshot.site == "deepswe")
        ).one()
    )


def test_unchanged_raw_not_saved(db_session: Session) -> None:
    collect_all(db_session, all_sites().fetcher(), NOW)
    rows = score_count(db_session)
    later = NOW + timedelta(days=1)
    result = collect_all(db_session, all_sites().fetcher(), later)
    assert set(result.values()) == {"unchanged"}
    assert score_count(db_session) == rows
    assert set(snapshots(db_session).values()) == {1}
    # the site was seen again today, so the stale alert measures from this fetch
    fetched = db_session.scalars(select(BenchmarkSnapshot.fetched_at)).all()
    assert set(fetched) == {later}


def test_changed_raw_adds_a_snapshot(db_session: Session) -> None:
    collect_all(db_session, all_sites().fetcher(), NOW)
    changed = all_sites()
    changed.routes.insert(
        0,
        (
            "data/20261025/table.csv",
            lambda _r: reply(
                200, "model,coding\nclaude-fable-5.1,50.0\n", "text/csv; charset=utf-8"
            ),
        ),
    )
    result = collect_all(db_session, changed.fetcher(), NOW + timedelta(days=1))
    assert result["livebench"] == "saved" and result["deepswe"] == "unchanged"
    assert snapshots(db_session)["livebench"] == 2


def test_html_response_is_drift_and_keeps_last_good(db_session: Session) -> None:
    collect_all(db_session, all_sites().fetcher(), NOW)
    before = db_session.scalars(
        select(BenchmarkScore.id).where(BenchmarkScore.site == "deepswe")
    ).all()
    router = Router()
    deepswe_routes(router, html=True)
    livebench_routes(router, table="model,coding\nclaude-fable-5.1,50.0\n")
    lmarena_routes(router)
    artificial_analysis_routes(router)
    result = collect_all(db_session, router.fetcher(), NOW + timedelta(days=1))
    assert result["deepswe"] == "selector_drift"
    assert result["livebench"] == "saved"
    after = db_session.scalars(
        select(BenchmarkScore.id).where(BenchmarkScore.site == "deepswe")
    ).all()
    assert after == before
    assert snapshots(db_session)["deepswe"] == 1


def test_one_site_failing_does_not_block_the_others(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(KEY)

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(deepswe, "fetch", boom)
    result = collect_all(db_session, all_sites().fetcher(), NOW)
    assert result["artificial_analysis"] == "config_error"
    assert result["deepswe"] == "error"
    assert result["livebench"] == result["lmarena"] == "saved"
    assert set(snapshots(db_session)) == {"livebench", "lmarena"}


def test_each_site_is_committed_on_its_own(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    commits: list[set[str]] = []
    real_commit = db_session.commit

    def spy() -> None:
        commits.append(set(db_session.scalars(select(BenchmarkSnapshot.site)).all()))
        real_commit()

    monkeypatch.setattr(db_session, "commit", spy)
    monkeypatch.setattr(
        artificial_analysis, "fetch", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    result = collect_all(db_session, all_sites().fetcher(), NOW)
    assert result["artificial_analysis"] == "error"
    # one commit per saved site, each right after that site's save
    assert [len(c) for c in commits] == [1, 2, 3]
    # the failure afterwards rolls back nothing that was committed
    assert set(snapshots(db_session)) == {"deepswe", "livebench", "lmarena"}


def make_snapshot(session: Session, site: str, fetched_at: datetime) -> None:
    session.add(
        BenchmarkSnapshot(site=site, release="x", fetched_at=fetched_at, sha256=site, raw={})
    )
    session.flush()


def test_check_benchmarks_stale_after_48h(db_session: Session) -> None:
    make_snapshot(db_session, "deepswe", NOW - timedelta(hours=49))
    make_snapshot(db_session, "livebench", NOW - timedelta(hours=47))
    make_snapshot(db_session, "lmarena", NOW - timedelta(minutes=5))
    findings = check_benchmarks(db_session, now=NOW)
    assert [(f.key, f.severity) for f in findings] == [
        ("benchmark_stale:deepswe", Severity.WARNING)
    ]
    assert findings[0].title == f"{deepswe.TITLE} 벤치마크가 48시간째 갱신되지 않았습니다"


def test_check_benchmarks_skips_artificial_analysis_without_key(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_snapshot(db_session, "artificial_analysis", NOW - timedelta(days=5))
    assert [f.key for f in check_benchmarks(db_session, now=NOW)] == [
        "benchmark_stale:artificial_analysis"
    ]
    assert artificial_analysis.TITLE in check_benchmarks(db_session, now=NOW)[0].title
    monkeypatch.delenv(KEY)
    assert check_benchmarks(db_session, now=NOW) == []


def test_check_benchmarks_is_quiet_before_the_first_collection(db_session: Session) -> None:
    assert check_benchmarks(db_session, now=NOW) == []
    findings = run_checks(db_session, now=NOW, queue_length=0)
    assert not [f for f in findings if f.key.startswith("benchmark_stale")]
