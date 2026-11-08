"""Terminal-Bench, Epoch AI, OSWorld 2.0 and τ²-bench collectors on responses recorded
2026-11-08 (trimmed), without network."""

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import BenchmarkScore, BenchmarkSnapshot
from news_insight.benchmarks.service import collect_all
from news_insight.benchmarks.sources import (
    BenchmarkError,
    NotModified,
    epoch,
    lmarena,
    osworld,
    tau2,
    terminal_bench,
)
from news_insight.public.benchmarks import benchmark_changes, preview
from tests.benchmarks.fakes import (
    EPOCH_ETAG,
    TAU2_SHA,
    FakeClock,
    Router,
    TbRouter,
    all_sites,
    epoch_routes,
    fixture_json,
    fixture_text,
    osworld_routes,
    reply,
    tau2_routes,
)

NOW = datetime(2026, 11, 8, 3, 30, tzinfo=UTC)
KEY = "SOURCE_SECRET_ARTIFICIAL_ANALYSIS_KEY"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    monkeypatch.setattr(lmarena, "_sleep", clock.sleep)
    monkeypatch.setattr(terminal_bench, "_sleep", clock.sleep)


# ---- Terminal-Bench ----------------------------------------------------------------------


def test_terminal_bench_reads_three_boards() -> None:
    snapshot = terminal_bench.fetch(TbRouter().fetcher(), NOW)
    assert snapshot.site == "terminal_bench"
    assert snapshot.raw["updated"] == {
        "4.0": "2026-10-23",
        "3.0": "2026-09-03",
        "2.1": "2026-09-03",
    }
    assert snapshot.release == "2026-10-23"
    assert [b for b in snapshot.raw["boards"]] == ["4.0", "3.0", "2.1"]
    top = next(r for r in snapshot.rows if r.board == "4.0" and r.extra["rank"] == 1)
    assert (top.model_raw, top.config, top.org, top.value) == (
        "Opus 5.5",
        "max",
        "Anthropic",
        64.85,
    )
    assert top.ci_low == pytest.approx(61.74) and top.ci_high == pytest.approx(67.96)
    assert top.extra["agent"] == "Claude Code" and top.extra["agent_org"] == "Anthropic"
    assert top.extra["label"] == "Claude Code · Opus 5.5"
    assert top.extra["total_cost_usd"] == 4718.65 and top.extra["total_tokens"] == 8034082467
    assert top.extra["pass_at_5"] == 0.7879 and top.extra["date"] == "2026-09-22"


def test_terminal_bench_default_view_keeps_each_model_and_agents_best_effort() -> None:
    snapshot = terminal_bench.fetch(TbRouter().fetcher(), NOW)
    rows = [r for r in snapshot.rows if r.board == "4.0"]
    assert len(rows) == 12
    shown = [
        (r.extra["default_rank"], r.extra["agent"], r.model_raw, r.config)
        for r in rows
        if "default_rank" in r.extra
    ]
    # GPT-6 Astra's xhigh/high/medium and Fable 5.1's lower efforts are left out; ties share
    assert shown == [
        (1, "Claude Code", "Opus 5.5", "max"),
        (2, "Claude Code", "Sonnet 5.5", "max"),
        (3, "Codex", "GPT-6 Astra", "max"),
        (3, "Codex", "GPT-6.1 Sol", "max"),
        (5, "Claude Code", "Fable 5.1", "max"),
        (6, "Claude Code", "Opus 5", "xhigh"),
    ]


def test_terminal_bench_date_is_the_boards_own_date_column() -> None:
    snapshot = terminal_bench.fetch(TbRouter().fetcher(), NOW)
    # 3.0 dates rows by metadata.release_date, 4.0 by metadata.date
    assert terminal_bench.date_key(snapshot.raw["boards"]["3.0"]["leaderboard"]) == "release_date"
    assert terminal_bench.date_key(snapshot.raw["boards"]["4.0"]["leaderboard"]) == "date"
    first = next(r for r in snapshot.rows if r.board == "3.0" and r.extra["rank"] == 1)
    assert first.extra["date"] == "2026-07-24"  # tbench.ai 3.0: "Jul 24, 2026"


def test_terminal_bench_tie_between_efforts_keeps_the_first_served() -> None:
    rows = [
        {
            "id": f"r{i}",
            "rank": 1,
            "metadata": {
                "agent_display": {"url": "https://a", "label": "Codex"},
                "model_display": {"url": "https://m", "label": "M"},
                "reasoning_effort": effort,
            },
            "metrics": {"accuracy": 50.0},
        }
        for i, effort in enumerate(("high", "max"))
    ]
    assert terminal_bench.default_view(rows) == {"r0": 1}


def _board(**changes: Any) -> str:
    data = fixture_json("terminal_bench_4_0_20261108.json")
    for path, value in changes.items():
        target = data
        *parents, last = path.split("__")
        for part in parents:
            target = target[int(part)] if part.isdigit() else target[part]
        if value is None:
            del target[last]
        else:
            target[last] = value
    return json.dumps(data)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"rows": []}, "no rows", id="empty"),
        pytest.param(
            {"leaderboard__rank_by": [{"accessor": "metrics.cost", "direction": "asc"}]},
            "rank_by",
            id="rank-by",
        ),
        pytest.param({"leaderboard__columns": []}, "column", id="columns"),
        pytest.param({"rows__0__metrics__accuracy": "64.8%"}, "accuracy", id="accuracy-text"),
        pytest.param({"rows__0__metrics__accuracy": 0.6485e3}, "accuracy", id="accuracy-range"),
        pytest.param({"rows__0__metadata": None}, "metadata", id="no-metadata"),
        pytest.param({"rows__0__metadata__reasoning_effort": 3}, "reasoning_effort", id="effort"),
        pytest.param({"leaderboard__updated_at": None}, "updated_at", id="no-date"),
    ],
)
def test_terminal_bench_schema_change_is_a_parse_error(
    changes: dict[str, Any], message: str
) -> None:
    router = TbRouter({"4-0-0": _board(**changes)})
    with pytest.raises(BenchmarkError) as err:
        terminal_bench.fetch(router.fetcher(), NOW)
    assert err.value.code == "parse_error"
    assert message in str(err.value)


def test_terminal_bench_error_answer_is_a_parse_error() -> None:
    body = '{"error":{"code":"server_error","message":"leaderboard read failed"}}'
    with pytest.raises(BenchmarkError) as err:
        terminal_bench.fetch(TbRouter({"main": body}).fetcher(), NOW)
    assert err.value.code == "parse_error"


def test_terminal_bench_retries_a_server_error_once() -> None:
    calls: list[int] = []
    router = TbRouter()
    good = fixture_text("terminal_bench_4_0_20261108.json")

    class Flaky(TbRouter):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            if request.url.params.get("name") == "4-0-0" and not calls:
                calls.append(1)
                return reply(500, '{"error":{"code":"server_error"}}', "application/json")
            return super().__call__(request)

    router = Flaky({"4-0-0": good})
    snapshot = terminal_bench.fetch(router.fetcher(), NOW)
    assert calls == [1] and snapshot.raw["updated"]["4.0"] == "2026-10-23"


# ---- OSWorld 2.0 -------------------------------------------------------------------------


def test_osworld_default_view_follows_the_sites_filters() -> None:
    snapshot = osworld.fetch(osworld_routes(Router()).fetcher(), NOW)
    assert snapshot.raw["updated"] == {"main": "2026-10-15"} and snapshot.release == "2026-10-15"
    assert len(snapshot.rows) == 11
    shown = sorted(
        (r.extra["default_rank"], r.model_raw, r.config, r.extra["release_version"], r.value)
        for r in snapshot.rows
        if "default_rank" in r.extra
    )
    # e2e only (Sai is an agent), 500 steps (not Opus 4.7's 150), the full set (not offline);
    # MuseSpark 1.2 has no official flag and still shows; MiniMax and Kimi tie on binary
    # accuracy and the partial score decides
    assert shown == [
        (1, "Claude Opus 5", "max", "v2.1", 44.33),
        (2, "MuseSpark 1.3", "max", "v2.1", 39.25),
        (3, "Claude Opus 5", "high", "v2026.08.08", 28.98),
        (4, "Claude Opus 4.8", "max", "v2026.06.24", 20.6),
        (5, "MuseSpark 1.2", "xhigh", "v2.1", 15.84),
        (6, "Claude Opus 4.7", "max", "v2026.06.24", 13.9),
        (7, "MiniMax M3", "enabled", "v2026.06.24", 4.6),
        (8, "Kimi 2.6", "enabled", "v2026.06.24", 4.6),
    ]
    opus47 = next(r for r in snapshot.rows if r.extra.get("default_rank") == 6)
    assert opus47.org == "Anthropic" and opus47.extra["tool_setting"] == "standard"
    assert round(opus47.extra["cost_per_task"], 1) == 35.8  # estimated cost over 108 tasks
    assert opus47.extra["partial_score"] == 49.1 and opus47.extra["step_budget"] == 500
    sai = next(r for r in snapshot.rows if r.model_raw.startswith("Sai"))
    assert "default_rank" not in sai.extra and sai.org == "Simular"
    assert sai.extra["cost_per_task"] == 14.34


def test_osworld_without_results_is_a_parse_error() -> None:
    router = osworld_routes(Router(), body=json.dumps({"updatedAt": "2026-10-15", "results": []}))
    with pytest.raises(BenchmarkError) as err:
        osworld.fetch(router.fetcher(), NOW)
    assert err.value.code == "parse_error"


# ---- Epoch AI ----------------------------------------------------------------------------


def test_epoch_keeps_the_boards_and_ranks_the_best_run_per_model() -> None:
    snapshot = epoch.fetch(epoch_routes(Router()).fetcher(), NOW, None)
    assert snapshot.raw["etag"] == EPOCH_ETAG
    assert set(snapshot.raw["updated"]) == {board.key for board in epoch.BOARDS}
    assert "Creative Commons Attribution" in snapshot.raw["readme"]
    gpqa = [r for r in snapshot.rows if r.board == "gpqa_diamond"]
    # nine runs, the leader's weaker second run folded into its best
    assert len(gpqa) == 8
    assert [r.extra["default_rank"] for r in gpqa] == list(range(1, 9))
    assert gpqa[0].model_raw == "Gemini 4 Argon (high)" and round(gpqa[0].value, 3) == 0.964
    assert (
        gpqa[0].extra["unit"] == "percent"
        and gpqa[0].extra["model_version"] == "gemini-4-argon_high"
    )
    eci = [r for r in snapshot.rows if r.board == "eci"]
    assert [r.model_raw for r in eci[:3]] == ["GPT-6 Astra", "GPT-6.1 Sol", "Claude Opus 5.5"]
    assert eci[0].value == 169.07 and (eci[0].ci_low, eci[0].ci_high) == (166.16, 172.28)
    metr = [r for r in snapshot.rows if r.board == "metr_time_horizons"]
    assert metr[0].extra["unit"] == "minutes" and metr[0].ci_high is not None
    assert metr[0].extra["source"].startswith("https://metr.org/")


def test_epoch_names_models_as_the_site_does() -> None:
    snapshot = epoch.fetch(epoch_routes(Router()).fetcher(), NOW, None)
    names = {r.extra["model_version"]: r.model_raw for r in snapshot.rows if r.board != "eci"}
    # the site's "Unique display name" (benchmarked_models.csv), not the zip's display name
    assert names["gemini-3.1-pro-preview_high"] == "Gemini 3.1 Pro Preview (high)"
    # without that file the zip's metadata stands in
    plain = epoch.fetch(epoch_routes(Router(), names=False).fetcher(), NOW, None)
    fallback = {r.extra["model_version"]: r.model_raw for r in plain.rows if r.board != "eci"}
    assert fallback["gemini-3.1-pro-preview_high"] == "Gemini 3.1 Pro Preview"


def test_epoch_unchanged_etag_downloads_nothing() -> None:
    router = epoch_routes(Router())
    with pytest.raises(NotModified):
        epoch.fetch(router.fetcher(), NOW, {"etag": EPOCH_ETAG})
    assert [r.headers.get("if-none-match") for r in router.requests] == [EPOCH_ETAG]
    # another ETag: the zip is downloaded again
    snapshot = epoch.fetch(router.fetcher(), NOW, {"etag": '"older"'})
    assert snapshot.raw["etag"] == EPOCH_ETAG


def test_epoch_missing_board_file_is_a_parse_error() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("README.md", "x")
        archive.writestr("model_metadata.csv", "model_version,display_name\n")
    router = Router().add(
        "=https://epoch.ai/data/benchmark_data.zip",
        httpx.Response(200, headers={"content-type": "application/zip"}, content=buf.getvalue()),
    )
    with pytest.raises(BenchmarkError) as err:
        epoch.fetch(router.fetcher(), NOW, None)
    assert err.value.code == "parse_error" and "eci_scores.csv" in str(err.value)


def test_epoch_html_instead_of_the_zip_is_drift() -> None:
    router = Router().add("benchmark_data.zip", reply(200, "<html></html>", "text/html"))
    with pytest.raises(BenchmarkError) as err:
        epoch.fetch(router.fetcher(), NOW, None)
    assert err.value.code == "selector_drift"


# ---- τ²-bench ----------------------------------------------------------------------------


def test_tau2_boards_from_two_text_submissions_and_one_voice() -> None:
    router = tau2_routes(Router())
    snapshot = tau2.fetch(router.fetcher(), NOW, None)
    assert snapshot.raw["commit"] == TAU2_SHA and snapshot.release == "2026-11-04"
    assert snapshot.raw["pending"] == []
    by_board: dict[str, list[tuple[str, float]]] = {}
    for row in snapshot.rows:
        by_board.setdefault(row.board, []).append((row.model_raw, round(row.value, 1)))
    # Claude Opus 5 ran banking only, so it has no overall and no domain rows
    assert by_board == {
        "overall": [("Claude Opus 4.5", 85.3)],
        "retail": [("Claude Opus 4.5", 79.6)],
        "airline": [("Claude Opus 4.5", 84.0)],
        "telecom": [("Claude Opus 4.5", 92.3)],
        "banking_knowledge": [("Claude Opus 4.5", 24.7), ("Claude Opus 5", 48.7)],
        "voice": [("Pine Voice 1.0", 87.3)],
    }
    banking = {r.model_raw: r for r in snapshot.rows if r.board == "banking_knowledge"}
    assert banking["Claude Opus 5"].extra["default_rank"] == 1
    assert banking["Claude Opus 4.5"].extra["default_rank"] == 2
    opus5 = banking["Claude Opus 5"]
    assert opus5.extra["submitting_org"] == "Sierra" and opus5.extra["verified"] is True
    assert opus5.extra["retrieval_config"] == "alltools" and opus5.config == "max"
    assert opus5.extra["pass_4"] == pytest.approx(31.96, abs=0.01)
    voice = next(r for r in snapshot.rows if r.board == "voice")
    assert voice.extra["voice_provider"] == "Pine AI" and voice.extra["modality"] == "voice"
    # one API call for the commit, one for the listing, then raw files only: 2 + 1 + 3
    assert len(router.requests) == 6
    assert sum("api.github.com" in str(r.url) for r in router.requests) == 2
    assert not any("authorization" in r.headers for r in router.requests)
    assert snapshot.raw["updated"]["banking_knowledge"] == "2026-08-04"


def test_tau2_same_commit_skips_everything() -> None:
    first = tau2.fetch(tau2_routes(Router()).fetcher(), NOW, None)
    router = tau2_routes(Router())
    with pytest.raises(NotModified):
        tau2.fetch(router.fetcher(), NOW, first.raw)
    assert len(router.requests) == 1


def test_tau2_new_commit_fetches_only_changed_submissions() -> None:
    first = tau2.fetch(tau2_routes(Router()).fetcher(), NOW, None)
    previous = json.loads(json.dumps(first.raw))
    # one submission's folder changed since: its SHA in the stored snapshot is older
    previous["submissions"]["claude-opus-5_sierra_2026-08-04"]["sha"] = "older"
    router = tau2_routes(Router(), sha="f" * 40)
    second = tau2.fetch(router.fetcher(), NOW, previous)
    fetched = [
        str(r.url).rsplit("/", 2)[-2] for r in router.requests if "submission.json" in str(r.url)
    ]
    assert fetched == ["claude-opus-5_sierra_2026-08-04"]
    # the manifest's SHA is unchanged too: not downloaded again
    assert not any("manifest.json" in str(r.url) for r in router.requests)
    assert {r.model_raw for r in second.rows} == {r.model_raw for r in first.rows}


def test_tau2_budget_leaves_the_rest_for_the_next_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tau2, "MAX_CALLS", 4)  # commit, listing, manifest, one submission
    snapshot = tau2.fetch(tau2_routes(Router()).fetcher(), NOW, None)
    assert snapshot.raw["pending"] == [
        "claude-opus-5_sierra_2026-08-04",
        "pine-voice-1-0_pineai_2026-10-27",
    ]
    monkeypatch.setattr(tau2, "MAX_CALLS", 60)
    # the same commit again: still fetched, because submissions are pending
    router = tau2_routes(Router())
    later = tau2.fetch(router.fetcher(), NOW, snapshot.raw)
    assert later.raw["pending"] == [] and {r.board for r in later.rows} >= {"voice"}
    assert sum("submission.json" in str(r.url) for r in router.requests) == 2


def test_tau2_marks_unverified_and_custom_as_the_site_does() -> None:
    sub = tau2.trim(fixture_json("tau2_claude-opus-5_sierra_2026-08-04.json"))
    assert tau2.verified(sub, "text")
    assert not tau2.verified({**sub, "trajectories_available": False}, "text")
    # voice has no trajectories to check
    assert tau2.verified({**sub, "trajectories_available": False}, "voice")
    custom = {
        **sub,
        "submission_type": "custom",
        "verification": {"modified_prompts": True, "omitted_questions": False},
    }
    assert tau2.verified(custom, "text")
    entries = [("a", "text", sub), ("b", "text", custom)]
    assert [f for f, _ in tau2.default_view(entries, "banking_knowledge")] == ["a"]


def test_tau2_manifest_without_submissions_is_a_parse_error() -> None:
    router = tau2_routes(Router())
    router.routes.insert(0, ("manifest.json", lambda _r: reply(200, "{}", "text/plain")))
    with pytest.raises(BenchmarkError) as err:
        tau2.fetch(router.fetcher(), NOW, None)
    assert err.value.code == "parse_error"


# ---- with the database -------------------------------------------------------------------


@pytest.mark.db
def test_schema_change_keeps_the_last_good_snapshot(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(KEY, "test-key")
    collect_all(db_session, all_sites().fetcher(), NOW)
    before = db_session.scalars(
        select(BenchmarkScore.id).where(BenchmarkScore.site == "terminal_bench")
    ).all()
    router = all_sites()
    assert isinstance(router, TbRouter)
    router.tb_bodies["4-0-0"] = _board(leaderboard__rank_by=[])
    result = collect_all(db_session, router.fetcher(), NOW + timedelta(days=1))
    assert result["terminal_bench"] == "parse_error"
    assert any("terminal_bench: parse_error" in m for m in caplog.messages)
    after = db_session.scalars(
        select(BenchmarkScore.id).where(BenchmarkScore.site == "terminal_bench")
    ).all()
    assert after == before


@pytest.mark.db
def test_unchanged_etag_and_commit_mark_the_snapshot_seen(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(KEY, "test-key")
    collect_all(db_session, all_sites().fetcher(), NOW)
    later = NOW + timedelta(days=1)
    router = all_sites()
    result = collect_all(db_session, router.fetcher(), later)
    assert result["epoch"] == result["tau2"] == "unchanged"
    # the zip was asked for with its ETag (answered 304); τ² stopped after the commit lookup
    zip_requests = [r for r in router.requests if "benchmark_data.zip" in str(r.url)]
    assert [r.headers.get("if-none-match") for r in zip_requests] == [EPOCH_ETAG]
    assert sum("tau2-bench" in str(r.url) for r in router.requests) == 1
    seen = dict(
        db_session.execute(
            select(BenchmarkSnapshot.site, BenchmarkSnapshot.fetched_at).where(
                BenchmarkSnapshot.site.in_(["epoch", "tau2"])
            )
        )
        .tuples()
        .all()
    )
    assert seen == {"epoch": later, "tau2": later}
    count = db_session.scalar(select(func.count()).select_from(BenchmarkSnapshot))
    assert count == 8


@pytest.mark.db
def test_one_new_source_failing_does_not_block_the_others(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(KEY, "test-key")
    router = all_sites()
    router.routes.insert(0, ("osworld-v2.xlang.ai", lambda _r: reply(503, "down", "text/plain")))
    result = collect_all(db_session, router.fetcher(), NOW)
    assert result["osworld"] == "http_error"
    assert {k: v for k, v in result.items() if k != "osworld"} == dict.fromkeys(
        [k for k in result if k != "osworld"], "saved"
    )


@pytest.mark.db
def test_spotlight_hears_only_eci_and_terminal_bench_4(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A move on any board of the newer sites reaches the spotlight only from Epoch's ECI and
    Terminal-Bench 4.0 (Epoch's other boards and the agent boards would flood it)."""
    monkeypatch.setenv(KEY, "test-key")
    collect_all(db_session, all_sites().fetcher(), NOW)
    # the next day every board of the newer sites reverses its order
    for snapshot in db_session.scalars(
        select(BenchmarkSnapshot).where(
            BenchmarkSnapshot.site.in_(["epoch", "terminal_bench", "osworld", "tau2"])
        )
    ):
        clone = BenchmarkSnapshot(
            site=snapshot.site,
            release=snapshot.release,
            fetched_at=NOW + timedelta(days=1),
            sha256=f"next-{snapshot.site}",
            raw={},
        )
        db_session.add(clone)
        db_session.flush()
        for score in db_session.scalars(
            select(BenchmarkScore).where(BenchmarkScore.snapshot_id == snapshot.id)
        ):
            extra = dict(score.extra)
            if "default_rank" in extra:
                extra["default_rank"] = 1000 - extra["default_rank"]
            db_session.add(
                BenchmarkScore(
                    snapshot_id=clone.id,
                    site=score.site,
                    board=score.board,
                    model_raw=score.model_raw,
                    org=score.org,
                    config=score.config,
                    metric=score.metric,
                    value=score.value,
                    extra=extra,
                )
            )
    db_session.flush()
    changes = benchmark_changes(db_session, now=NOW + timedelta(days=1, hours=1))
    boards = {(c["site"], c["board"]) for c in changes["changes"] + changes["new_models"]}
    assert boards == {("Terminal-Bench", "4.0"), ("Epoch AI", "eci")}
    # a Terminal-Bench entry reads as harness · model
    assert any(c["model"] == "Claude Code · Opus 5.5" for c in changes["changes"])


def test_dry_run_preview_of_the_newer_sites() -> None:
    snapshot = terminal_bench.fetch(TbRouter().fetcher(), NOW)
    board = preview(snapshot)["4.0"]
    assert [(e["rank"], e["site_rank"], e["model"]) for e in board[:4]] == [
        (1, 1, "Claude Code · Opus 5.5"),
        (2, 2, "Claude Code · Sonnet 5.5"),
        (3, 3, "Codex · GPT-6 Astra"),
        (4, 3, "Codex · GPT-6.1 Sol"),
    ]
