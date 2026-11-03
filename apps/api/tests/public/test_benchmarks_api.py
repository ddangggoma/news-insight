from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import AiModel, BenchmarkScore, BenchmarkSnapshot
from news_insight.benchmarks.sources import artificial_analysis, deepswe, livebench, lmarena
from news_insight.public.benchmarks import benchmark_changes, benchmarks_view
from tests.public.seed import NOW

pytestmark = pytest.mark.db

PATH = "/api/public/benchmarks"
Row = tuple[str, str, float]  # (board, model, value)


def snapshot(
    session: Session,
    site: str,
    rows: list[tuple[Any, ...]],
    *,
    hours_ago: float = 3,
    release: str = "r1",
    metric: str = "rating",
) -> BenchmarkSnapshot:
    """rows are (board, model, value[, metric[, config[, model_id]]])."""
    count = session.query(BenchmarkSnapshot).count()
    snap = BenchmarkSnapshot(
        site=site,
        release=release,
        fetched_at=NOW - timedelta(hours=hours_ago),
        sha256=f"{site}-{count}",
        raw={},
    )
    session.add(snap)
    session.flush()
    for board, model, value, *rest in rows:
        row_metric = rest[0] if rest else metric
        config = rest[1] if len(rest) > 1 else None
        model_id = rest[2] if len(rest) > 2 else None
        session.add(
            BenchmarkScore(
                snapshot_id=snap.id,
                site=site,
                board=board,
                model_raw=model,
                model_id=model_id,
                org=None,
                config=config,
                metric=row_metric,
                value=value,
                extra={"vote_count": 10},
            )
        )
    session.flush()
    return snap


def site_of(body: list[dict[str, Any]], site: str) -> dict[str, Any]:
    return next(s for s in body if s["site"] == site)


def ranked(site: dict[str, Any], board: str) -> list[tuple[str, int, str | None, int]]:
    rows = [r for r in site["rows"] if r["board"] == board and r["rank"] is not None]
    return [(r["model"], r["rank"], r["change"], r["change_by"]) for r in rows]


def test_view_marks_stale_after_48h(db_session: Session) -> None:
    snapshot(db_session, lmarena.SITE, [("text", "a", 1500.0)], hours_ago=47)
    snapshot(db_session, deepswe.SITE, [("v1.1", "m", 0.5, "pass_at_1")], hours_ago=49)
    by_site = {s.site: s for s in benchmarks_view(db_session, now=NOW)}
    assert by_site[lmarena.SITE].stale is False
    assert by_site[deepswe.SITE].stale is True
    assert lmarena.SITE in by_site and artificial_analysis.SITE not in by_site  # never collected


def test_latest_snapshot_is_the_one_seen_last(db_session: Session) -> None:
    # fetched_at means "last seen": the older-created snapshot seen again later is current
    snapshot(db_session, lmarena.SITE, [("text", "old", 1400.0)], hours_ago=30, release="a")
    snapshot(db_session, lmarena.SITE, [("text", "new", 1500.0)], hours_ago=50, release="b")
    site = benchmarks_view(db_session, now=NOW)[0]
    assert site.release == "a"
    assert [r.model for r in site.rows] == ["old"]


def test_rank_change_against_previous_snapshot(db_session: Session) -> None:
    snapshot(
        db_session,
        lmarena.SITE,
        [("text", "a", 1500.0), ("text", "b", 1490.0), ("text", "c", 1480.0)],
        hours_ago=30,
    )
    snapshot(
        db_session,
        lmarena.SITE,
        [
            ("text", "a", 1500.0),
            ("text", "c", 1495.0),
            ("text", "b", 1485.0),
            ("text", "d", 1470.0),
        ],
        hours_ago=3,
    )
    body = [s.model_dump(mode="json") for s in benchmarks_view(db_session, now=NOW)]
    assert ranked(site_of(body, lmarena.SITE), "text") == [
        ("a", 1, "same", 0),
        ("c", 2, "up", 1),
        ("b", 3, "down", 1),
        ("d", 4, "new", 0),
    ]


def test_first_snapshot_has_rank_but_no_change(db_session: Session) -> None:
    snapshot(db_session, lmarena.SITE, [("text", "a", 1500.0), ("text", "b", 1400.0)])
    rows = benchmarks_view(db_session, now=NOW)[0].rows
    assert [(r.rank, r.change, r.change_by) for r in rows] == [(1, None, 0), (2, None, 0)]


def test_a_board_missing_before_has_no_change(db_session: Session) -> None:
    snapshot(db_session, lmarena.SITE, [("text", "a", 1500.0)], hours_ago=30)
    snapshot(db_session, lmarena.SITE, [("text", "a", 1500.0), ("webdev", "a", 1300.0)])
    body = [s.model_dump(mode="json") for s in benchmarks_view(db_session, now=NOW)]
    site = site_of(body, lmarena.SITE)
    assert site["boards"] == ["text", "webdev"]
    assert ranked(site, "text") == [("a", 1, "same", 0)]
    assert ranked(site, "webdev") == [("a", 1, None, 0)]


def test_agent_board_ranks_by_score_and_other_metrics_stay_unranked(db_session: Session) -> None:
    snapshot(
        db_session,
        lmarena.SITE,
        [
            ("agent", "x", 0.4, "score"),
            ("agent", "y", 0.6, "score"),
            ("agent", "y", 9.0, "cost_per_task_p50"),
        ],
    )
    rows = benchmarks_view(db_session, now=NOW)[0].rows
    by = {(r.model, r.metric): r for r in rows}
    assert by[("y", "score")].rank == 1 and by[("x", "score")].rank == 2
    assert by[("y", "cost_per_task_p50")].rank is None
    assert by[("y", "cost_per_task_p50")].change is None


def test_deepswe_ranks_each_model_by_its_best_config(db_session: Session) -> None:
    snapshot(
        db_session,
        deepswe.SITE,
        [
            ("v1.1", "alpha", 0.30, "pass_at_1", "low"),
            ("v1.1", "alpha", 0.55, "pass_at_1", "high"),
            ("v1.1", "beta", 0.50, "pass_at_1", "high"),
        ],
    )
    rows = benchmarks_view(db_session, now=NOW)[0].rows
    assert len(rows) == 3  # every stored row comes back
    ranks = {(r.model, r.config): r.rank for r in rows}
    assert ranks == {("alpha", "high"): 1, ("alpha", "low"): None, ("beta", "high"): 2}


def test_models_are_one_entry_across_spellings_and_configs(db_session: Session) -> None:
    model = AiModel(name="claude-opus-5", org="Anthropic")
    db_session.add(model)
    db_session.flush()
    snapshot(
        db_session,
        lmarena.SITE,
        [
            ("text", "claude-opus-5 (High)", 1500.0, "rating", "High"),
            ("text", "Claude Opus 5 (Low)", 1450.0, "rating", "Low"),
            ("text", "other", 1480.0),
        ],
    )
    rows = benchmarks_view(db_session, now=NOW)[0].rows
    by_model = {r.model: r for r in rows}
    assert by_model["claude-opus-5 (High)"].rank == 1
    assert by_model["Claude Opus 5 (Low)"].rank is None  # same model, lower config
    assert by_model["other"].rank == 2


def test_livebench_gets_a_derived_overall_row_without_the_cost_metric(db_session: Session) -> None:
    snapshot(
        db_session,
        livebench.SITE,
        [
            ("main", "m1", 80.0, "coding"),
            ("main", "m1", 60.0, "reasoning"),
            ("main", "m1", 3.0, livebench.COST_METRIC),
            ("main", "m2", 50.0, "coding"),
            ("main", "m2", 52.0, "reasoning"),
        ],
    )
    rows = benchmarks_view(db_session, now=NOW)[0].rows
    overall = {r.model: r for r in rows if r.metric == "overall"}
    assert overall["m1"].value == pytest.approx(70.0)  # cost_per_success is not averaged in
    assert overall["m1"].rank == 1 and overall["m2"].rank == 2
    assert overall["m1"].extra["derived"] is True
    assert overall["m1"].extra["categories"] == ["coding", "reasoning"]
    assert len(rows) == 5 + 2  # the stored rows stay, unranked
    assert all(r.rank is None for r in rows if r.metric != "overall")


def test_artificial_analysis_ranks_the_intelligence_index(db_session: Session) -> None:
    index = "artificial_analysis_intelligence_index"
    snapshot(
        db_session,
        artificial_analysis.SITE,
        [
            ("language", "p", 40.0, index),
            ("language", "q", 55.0, index),
            ("language", "q", 900.0, "median_output_tokens_per_second"),
        ],
    )
    site = benchmarks_view(db_session, now=NOW)[0]
    assert site.attribution == "Data: Artificial Analysis"
    assert ranked(site.model_dump(mode="json"), "language") == [
        ("q", 1, None, 0),
        ("p", 2, None, 0),
    ]


def test_attribution_present_for_artificial_analysis(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    snapshot(db_session, artificial_analysis.SITE, [("language", "q", 55.0)])
    body = public_client.get(PATH, headers=public_headers).json()
    site = site_of(body, artificial_analysis.SITE)
    assert site["attribution"] == "Data: Artificial Analysis"
    assert site["title"] == artificial_analysis.TITLE
    assert site["source_url"] == artificial_analysis.SOURCE_URL


def test_row_shape(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    model = AiModel(name="gem", org="Google")
    db_session.add(model)
    db_session.flush()
    snapshot(db_session, lmarena.SITE, [("text", "Gem (High)", 1500.0, "rating", "High", model.id)])
    body = public_client.get(PATH, headers=public_headers).json()
    assert set(site_of(body, lmarena.SITE)) == {
        "site",
        "title",
        "source_url",
        "license",
        "attribution",
        "release",
        "fetched_at",
        "stale",
        "boards",
        "rows",
    }
    row = site_of(body, lmarena.SITE)["rows"][0]
    assert row == {
        "board": "text",
        "model": "Gem (High)",
        "model_id": model.id,
        "org": "Google",  # the registry's, when the site gives none
        "config": "High",
        "metric": "rating",
        "value": 1500.0,
        "ci_low": None,
        "ci_high": None,
        "extra": {"vote_count": 10},
        "rank": 1,
        "change": None,
        "change_by": 0,
    }


def test_endpoint_needs_the_public_key(public_client: TestClient) -> None:
    assert public_client.get(PATH).status_code == 401


def test_empty_database_gives_an_empty_list(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    assert public_client.get(PATH, headers=public_headers).json() == []


def test_changes_only_inside_the_top_20(db_session: Session) -> None:
    before = [("text", f"m{i:02d}", 1600.0 - i) for i in range(1, 31)]
    after = [("text", f"m{i:02d}", 1600.0 - i) for i in range(1, 31)]
    after[0] = ("text", "m01", 1500.0)  # m01 falls to last place
    after[24] = ("text", "m25", 1599.5)  # m25 jumps from 25th to 1st
    after.append(("text", "fresh", 1599.0))  # brand new, 2nd; m02..m19 each move down one
    snapshot(db_session, lmarena.SITE, before, hours_ago=30)
    snapshot(db_session, lmarena.SITE, after, hours_ago=3)

    result = benchmark_changes(db_session, now=NOW)

    moves = {c["model"]: (c["from"], c["to"]) for c in result["changes"]}
    assert moves["m02"] == (2, 3) and moves["m19"] == (19, 20)
    assert set(moves) == {f"m{i:02d}" for i in range(2, 20)}  # m20 slipped out, m01 fell out
    assert all(c["site"] == "LMArena" and c["board"] == "text" for c in result["changes"])
    new = {n["model"]: n for n in result["new_models"]}
    assert set(new) == {"m25", "fresh"}  # m25 came in from 25th, fresh from nowhere
    assert new["m25"]["previous_rank"] == 25 and new["fresh"]["previous_rank"] is None
    assert new["m25"]["rank"] == 1 and new["fresh"]["rank"] == 2


def test_changes_empty_without_a_previous_snapshot(db_session: Session) -> None:
    snapshot(db_session, lmarena.SITE, [("text", "a", 1500.0)])
    assert benchmark_changes(db_session, now=NOW) == {"changes": [], "new_models": []}


def test_changes_skip_moves_older_than_two_days(db_session: Session) -> None:
    snapshot(
        db_session, lmarena.SITE, [("text", "a", 1500.0), ("text", "b", 1400.0)], hours_ago=200
    )
    snapshot(
        db_session, lmarena.SITE, [("text", "b", 1500.0), ("text", "a", 1400.0)], hours_ago=100
    )
    assert benchmark_changes(db_session, now=NOW) == {"changes": [], "new_models": []}


def test_changes_use_the_site_title(db_session: Session) -> None:
    snapshot(
        db_session,
        deepswe.SITE,
        [("v1.1", "a", 0.4, "pass_at_1"), ("v1.1", "b", 0.3, "pass_at_1")],
        hours_ago=30,
    )
    snapshot(
        db_session,
        deepswe.SITE,
        [("v1.1", "b", 0.5, "pass_at_1"), ("v1.1", "a", 0.4, "pass_at_1")],
        hours_ago=3,
    )
    result = benchmark_changes(db_session, now=NOW)
    assert {(c["site"], c["model"], c["from"], c["to"]) for c in result["changes"]} == {
        ("DeepSWE", "b", 2, 1),
        ("DeepSWE", "a", 1, 2),
    }
