from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import AiModel, BenchmarkScore, BenchmarkSnapshot
from news_insight.benchmarks.service import collect_all
from news_insight.benchmarks.sources import forecastbench, lmarena, simplebench
from news_insight.ops.checks import check_benchmarks, run_checks
from news_insight.ops.models import Severity
from tests.benchmarks.fakes import (
    FORECASTBENCH_URL,
    HTML_BODY,
    SIMPLEBENCH_URL,
    FakeClock,
    Router,
    all_sites,
    livebench_routes,
    lmarena_routes,
    reply,
)

pytestmark = pytest.mark.db

SITES = (
    "livebench",
    "lmarena",
    "terminal_bench",
    "epoch",
    "osworld",
    "tau2",
    "seal",
    "vals",
    "vending_bench",
    "simplebench",
    "forecastbench",
)

NOW = datetime(2026, 11, 3, 3, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
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
    assert result == dict.fromkeys(SITES, "saved")
    assert snapshots(db_session) == dict.fromkeys(SITES, 1)
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
        select(BenchmarkScore).where(BenchmarkScore.model_raw == "Claude Fable 5.2")
    ).first()
    assert unmatched is not None and unmatched.model_id is None
    assert unmatched.snapshot_id in set(
        db_session.scalars(
            select(BenchmarkSnapshot.id).where(BenchmarkSnapshot.site.in_(["simplebench", "vals"]))
        )
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
    assert result["livebench"] == "saved" and result["simplebench"] == "unchanged"
    assert snapshots(db_session)["livebench"] == 2


def test_html_response_is_drift_and_keeps_last_good(db_session: Session) -> None:
    collect_all(db_session, all_sites().fetcher(), NOW)
    before = db_session.scalars(
        select(BenchmarkScore.id).where(BenchmarkScore.site == "simplebench")
    ).all()
    router = Router()
    # the data script answers with a page of HTML (a login wall, a moved file)
    router.add(SIMPLEBENCH_URL, reply(200, HTML_BODY, "text/html"))
    livebench_routes(router, table="model,coding\nclaude-fable-5.1,50.0\n")
    lmarena_routes(router)
    result = collect_all(db_session, router.fetcher(), NOW + timedelta(days=1))
    assert result["simplebench"] == "selector_drift"
    assert result["livebench"] == "saved"
    after = db_session.scalars(
        select(BenchmarkScore.id).where(BenchmarkScore.site == "simplebench")
    ).all()
    assert after == before
    assert snapshots(db_session)["simplebench"] == 1


def test_one_site_failing_does_not_block_the_others(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(simplebench, "fetch", boom)
    router = all_sites()
    router.routes.insert(0, (FORECASTBENCH_URL, lambda _r: reply(503, "down", "text/plain")))
    result = collect_all(db_session, router.fetcher(), NOW)
    assert result["forecastbench"] == "http_error"
    assert result["simplebench"] == "error"
    assert result["livebench"] == result["lmarena"] == result["seal"] == "saved"
    assert set(snapshots(db_session)) == set(SITES) - {"simplebench", "forecastbench"}


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
        forecastbench, "fetch", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    monkeypatch.setattr(
        lmarena, "fetch", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    result = collect_all(db_session, all_sites().fetcher(), NOW)
    assert result["lmarena"] == result["forecastbench"] == "error"
    # one commit per saved site, each right after that site's save; a site that reads its
    # previous snapshot (epoch, tau2) also commits that read before it fetches
    assert [len(c) for c in commits] == [1, 2, 2, 3, 4, 4, 5, 6, 7, 8, 9]
    # the failure in the middle rolls back nothing that was committed
    assert set(snapshots(db_session)) == set(SITES) - {"lmarena", "forecastbench"}


def make_snapshot(session: Session, site: str, fetched_at: datetime) -> None:
    session.add(
        BenchmarkSnapshot(site=site, release="x", fetched_at=fetched_at, sha256=site, raw={})
    )
    session.flush()


def test_check_benchmarks_stale_after_48h(db_session: Session) -> None:
    make_snapshot(db_session, "simplebench", NOW - timedelta(hours=49))
    make_snapshot(db_session, "livebench", NOW - timedelta(hours=47))
    make_snapshot(db_session, "lmarena", NOW - timedelta(minutes=5))
    findings = check_benchmarks(db_session, now=NOW)
    assert [(f.key, f.severity) for f in findings] == [
        ("benchmark_stale:simplebench", Severity.WARNING)
    ]
    assert findings[0].title == f"{simplebench.TITLE} 벤치마크가 48시간째 갱신되지 않았습니다"


def test_check_benchmarks_ignores_the_sites_that_were_dropped(db_session: Session) -> None:
    """DeepSWE and Artificial Analysis are no longer collected: their old snapshots stay in the
    table and must not raise a stale alert for ever."""
    make_snapshot(db_session, "deepswe", NOW - timedelta(days=5))
    make_snapshot(db_session, "artificial_analysis", NOW - timedelta(days=5))
    assert check_benchmarks(db_session, now=NOW) == []


def test_check_benchmarks_is_quiet_before_the_first_collection(db_session: Session) -> None:
    assert check_benchmarks(db_session, now=NOW) == []
    findings = run_checks(db_session, now=NOW, queue_length=0)
    assert not [f for f in findings if f.key.startswith("benchmark_stale")]
