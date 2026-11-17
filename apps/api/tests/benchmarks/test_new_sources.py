"""Scale SEAL, Vals Index, Vending-Bench 2, SimpleBench and ForecastBench collectors on
responses recorded 2026-11-13 (trimmed), without network.

Each expected list is the head of what the site's own page showed that day, in the precision
it prints: labs.scale.com's board tables (Rank (UB), model, score ± CI), vals.ai's table (Rank,
Model, Accuracy, Cost / Test, Tokens / Test, Duration / Test), andonlabs.com's current
leaderboard (rank, model, money balance), simple-bench.com's MCQ table and forecastbench.org's
tournament table with anonymous teams hidden. The fixtures keep the first rows of each response,
so rows the sites show that were cut away are not expected here.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import BenchmarkScore, BenchmarkSnapshot
from news_insight.benchmarks.service import collect_all
from news_insight.benchmarks.sources import (
    BenchmarkError,
    ScoreRow,
    forecastbench,
    lmarena,
    seal,
    simplebench,
    terminal_bench,
    vals,
    vending_bench,
)
from news_insight.public.benchmarks import benchmark_changes, benchmarks_view, preview
from tests.benchmarks.fakes import (
    FORECASTBENCH_URL,
    HTML_BODY,
    SEAL_URL,
    SIMPLEBENCH_URL,
    VALS_URL,
    VENDING_URL,
    FakeClock,
    Router,
    all_sites,
    fixture_text,
    forecastbench_routes,
    reply,
    seal_routes,
    simplebench_routes,
    vals_routes,
    vending_routes,
)

NOW = datetime(2026, 11, 13, 3, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    monkeypatch.setattr(lmarena, "_sleep", clock.sleep)
    monkeypatch.setattr(terminal_bench, "_sleep", clock.sleep)


def code_of(call: Any, *args: Any) -> str:
    with pytest.raises(BenchmarkError) as err:
        call(*args)
    return err.value.code


def on_board(rows: list[ScoreRow], board: str) -> list[ScoreRow]:
    return [row for row in rows if row.board == board]


# ---- Scale SEAL --------------------------------------------------------------------------

# labs.scale.com/leaderboard/hle-diamond: Rank (UB), model, score, ± CI
SEAL_HLE = [
    (1, "claude-fable-5-2", "72.40", "2.68"),
    (2, "gpt-6-astra", "60.60", "3.00"),
    (3, "claude-opus-5-5", "55.00", "3.10"),
    (4, "gemini-4-argon", "53.20", "3.07"),
    (5, "claude-fable-5-1", "51.30", "3.10"),
]
# labs.scale.com/leaderboard/swe_bench_pro_public_v2, the Full tab: ranks are shared
SEAL_SWE_FULL = [
    (1, "Opus 5 (Claude Code) xhigh", "99.40"),
    (2, "Gemini 4 Argon (mini-swe-agent) high", "99.22"),
    (2, "Fable 5.1 (Claude Code) high", "99.10"),
    (3, "Kimi-K3 (mini-swe-agent) max", "97.70"),
    (4, "Inkling 2 Small", "97.66"),
    (5, "GPT-6-Astra (Codex) high", "96.90"),
    (5, "Muse Wonder 1.0 (mini-swe-agent) xhigh", "96.73"),
]


def test_seal_mirrors_the_boards_its_index_lists() -> None:
    router = seal_routes(Router())
    snapshot = seal.fetch(router.fetcher(), NOW)
    assert snapshot.site == "seal"
    # the index first, then one page per live board it lists (never the retired or safety ones)
    assert [str(r.url) for r in router.requests] == [
        SEAL_URL,
        f"{SEAL_URL}/hle-diamond",
        f"{SEAL_URL}/mcp_atlas",
        f"{SEAL_URL}/swe_bench_pro_public_v2",
    ]
    # a board with tabs is one board per tab, the tab the page opens on first
    assert snapshot.raw["order"] == [
        "hle-diamond",
        "mcp_atlas",
        "swe_bench_pro_public_v2:hard",
        "swe_bench_pro_public_v2:full",
    ]
    assert snapshot.raw["updated"] == {
        "hle-diamond": "2026-11-11",
        "mcp_atlas": "2026-11-06",
        "swe_bench_pro_public_v2:hard": "2026-11-06",
        "swe_bench_pro_public_v2:full": "2026-11-06",
    }
    assert snapshot.release == "2026-11-11"
    titles = {row.board: row.extra["board_title"] for row in snapshot.rows}
    assert titles == {
        "hle-diamond": "Humanity's Last Exam (Diamond)",
        "mcp_atlas": "MCP Atlas",
        "swe_bench_pro_public_v2:hard": "SWE-Bench Pro V2 HARD",
        "swe_bench_pro_public_v2:full": "SWE-Bench Pro V2 Full",
    }
    orders = {row.board: row.extra["board_order"] for row in snapshot.rows}
    assert [orders[key] for key in snapshot.raw["order"]] == [0, 1, 2, 3]


def test_seal_default_tables_equal_the_sites() -> None:
    snapshot = seal.fetch(seal_routes(Router()).fetcher(), NOW)
    hle = on_board(snapshot.rows, "hle-diamond")
    assert [
        (r.extra["default_rank"], r.model_raw, f"{r.value:.2f}", f"{r.extra['ci_half']:.2f}")
        for r in hle[:5]
    ] == SEAL_HLE
    top = hle[0]
    assert (top.org, top.metric, top.config) == ("anthropic", "score", None)
    assert top.ci_low == pytest.approx(69.72) and top.ci_high == pytest.approx(75.08)
    assert top.extra["is_new"] is True and top.extra["created"] == "2026-11-11"
    assert top.extra["entry"] == top.extra["label"] == "claude-fable-5-2"
    full = on_board(snapshot.rows, "swe_bench_pro_public_v2:full")
    assert [(r.extra["default_rank"], r.model_raw, f"{r.value:.2f}") for r in full[:7]] == (
        SEAL_SWE_FULL
    )
    ranked = preview(snapshot, top=3)["hle-diamond"]
    assert [(e["rank"], e["site_rank"], e["model"]) for e in ranked] == [
        (1, 1, "claude-fable-5-2"),
        (2, 2, "gpt-6-astra"),
        (3, 3, "claude-opus-5-5"),
    ]


def _category(board_id: str, category: str = "frontier", **more: Any) -> dict[str, Any]:
    return {"id": board_id, "name": board_id, "category": category, "deprecated": False, **more}


def test_seal_picks_the_named_boards_then_the_first_frontier_and_agentic_ones() -> None:
    listed = [
        _category("hss"),
        _category("distressbench", "safety"),
        _category("hle-diamond"),
        _category("drugdiscoverybench", "agentic"),
        _category("hil", "agentic"),
        _category("old", deprecated=True),
        _category("mcp_atlas", "agentic"),
        _category("swe_bench_pro_public_v2", "agentic", tabKey="full"),
        _category("swe_bench_pro_public_v2", "agentic", tabKey="hard"),
        _category("swe-atlas", "agentic"),
        _category("rli", "agentic"),
        _category("../etc"),
    ]
    assert [c["id"] for c in seal.pick_boards(listed)] == [
        "hss",
        "hle-diamond",
        "drugdiscoverybench",
        "hil",
        "mcp_atlas",
        "swe_bench_pro_public_v2",
    ]
    # the named boards are kept whatever their category; nothing else from "safety"
    only = [_category("mcp_atlas", "safety"), _category("fortress", "safety")]
    assert [c["id"] for c in seal.pick_boards(only)] == ["mcp_atlas"]


def test_seal_page_without_flight_data_is_drift() -> None:
    assert code_of(seal.fetch, seal_routes(Router(), index=HTML_BODY).fetcher(), NOW) == (
        "selector_drift"
    )
    router = seal_routes(Router(), pages={"mcp_atlas": HTML_BODY})
    assert code_of(seal.fetch, router.fetcher(), NOW) == "selector_drift"


def test_seal_entry_without_a_score_is_a_parse_error() -> None:
    page = fixture_text("seal_mcp_atlas_20261113.html").replace('\\"score\\":90.7', '\\"sc\\":1')
    assert page != fixture_text("seal_mcp_atlas_20261113.html")
    router = seal_routes(Router(), pages={"mcp_atlas": page})
    assert code_of(seal.fetch, router.fetcher(), NOW) == "parse_error"


def test_seal_deprecated_entry_is_kept_unranked() -> None:
    page = fixture_text("seal_mcp_atlas_20261113.html").replace(
        '\\"deprecated\\":false', '\\"deprecated\\":true', 1
    )
    snapshot = seal.fetch(seal_routes(Router(), pages={"mcp_atlas": page}).fetcher(), NOW)
    first, second = on_board(snapshot.rows, "mcp_atlas")[:2]
    assert "default_rank" not in first.extra and first.extra["deprecated"] is True
    assert second.extra["default_rank"] == 2


# ---- Vals Index --------------------------------------------------------------------------


def _vals_tokens(value: float) -> str:
    return f"{value / 1e6:.2f}m"


def _vals_duration(seconds: float) -> str:
    """vals.ai's Duration / Test: "43m42s", from an hour up "1h26m"."""
    if seconds >= 3600:
        minutes = round(seconds / 60)
        return f"{minutes // 60}h{minutes % 60:02d}m"
    whole = round(seconds)
    return f"{whole // 60}m{whole % 60:02d}s"


# vals.ai/benchmarks/vals_index: Rank, Model, Accuracy, Cost / Test, Tokens / Test, Duration
VALS = [
    (1, "Claude Fable 5.2", "71.31%", "$17.94", "31.31m", "43m42s"),
    (2, "Claude Sonnet 5.5", "70.85%", "$16.18", "78.59m", "1h26m"),
    (3, "Gemini 4 Carbon", "70.45%", "$10.51", "18.29m", "47m45s"),
    (4, "Claude Opus 5.5", "70.14%", "$24.77", "59.46m", "1h25m"),
    (5, "Gemini 4 Argon", "69.39%", "$13.37", "23.31m", "44m58s"),
    (6, "Gemini 4 Hydrogen", "68.49%", "$9.84", "41.19m", "32m05s"),
    (7, "Wonder Full", "66.79%", "$6.81", "18.37m", "59m19s"),
    (8, "GPT-6 Astra", "65.02%", "$21.28", "8.15m", "33m39s"),
]


def test_vals_default_table_equals_the_sites() -> None:
    router = vals_routes(Router())
    snapshot = vals.fetch(router.fetcher(), NOW)
    assert [str(r.url) for r in router.requests] == [VALS_URL]
    assert (snapshot.site, snapshot.release) == ("vals", "2026-11-11")
    assert snapshot.raw["updated"] == {"vals_index": "2026-11-11"}
    assert snapshot.raw["version"] == "2.2"
    assert len(snapshot.rows) == 12
    assert [
        (
            r.extra["default_rank"],
            r.model_raw,
            f"{r.value:.2f}%",
            f"${r.extra['cost_per_test']:.2f}",
            _vals_tokens(r.extra["tokens_per_test"]),
            _vals_duration(r.extra["latency"]),
        )
        for r in snapshot.rows[:8]
    ] == VALS
    top = snapshot.rows[0]
    assert (top.board, top.metric, top.org) == ("vals_index", "accuracy", "Anthropic")
    assert top.extra["entry"] == "anthropic/claude-fable-5-2"
    assert top.extra["stderr"] == 0.956
    assert [s["label"] for s in top.extra["sections"]] == ["Finance", "Coding", "Legal", "Tax"]
    # the open-weights models are the ones the site's "Open Weights" ranking lists
    assert [r.model_raw for r in snapshot.rows if r.extra.get("open_weights")] == [
        "Kimi K3.1 Pro",
        "DeepSeek V4.1 Flash 1017",
    ]


def test_vals_best_model_of_each_lab_is_the_first_of_its_company() -> None:
    """The site's opening bar ranking ("Showing best model from each lab")."""
    snapshot = vals.fetch(vals_routes(Router()).fetcher(), NOW)
    best: dict[str, str] = {}
    for row in snapshot.rows:
        best.setdefault(row.org or "", row.model_raw)
    assert list(best.items())[:5] == [
        ("Anthropic", "Claude Fable 5.2"),
        ("Google", "Gemini 4 Carbon"),
        ("Meta", "Wonder Full"),
        ("OpenAI", "GPT-6 Astra"),
        ("Moonshot AI", "Kimi K3.1 Pro"),
    ]


def test_vals_revives_astro_props() -> None:
    assert vals.revive([0, {"a": [0, 1], "b": [1, [[0, "x"], [0, {"c": [0, None]}]]]}]) == {
        "a": 1,
        "b": ["x", {"c": None}],
    }
    assert vals.revive([0]) is None  # an undefined
    assert vals.revive([3, "2026-11-11T00:00:00.000Z"]) == "2026-11-11T00:00:00.000Z"


def test_vals_page_without_its_islands_is_drift() -> None:
    assert code_of(vals.fetch, vals_routes(Router(), body=HTML_BODY).fetcher(), NOW) == (
        "selector_drift"
    )


def test_vals_ranking_without_positions_is_a_parse_error() -> None:
    page = fixture_text("vals_index_20261113.html").replace("&quot;position&quot;", "&quot;p&quot;")
    assert code_of(vals.fetch, vals_routes(Router(), body=page).fetcher(), NOW) == "parse_error"


# ---- Vending-Bench 2 ---------------------------------------------------------------------

# andonlabs.com/evals/vending-bench-2, Current leaderboard: model, money balance
VENDING = [
    (1, "Gemini 4 Carbon", "$16,484.21"),
    (2, "GPT-6 Astra", "$15,514.70"),
    (3, "GPT-6 Sol", "$14,427.85"),
    (4, "Gemini 4 Argon", "$13,718.16"),
    (5, "Claude Opus 5", "$11,181.87"),
    (6, "Claude Sonnet 5.5", "$11,165.28"),
]


def test_vending_bench_leaderboard_equals_the_sites() -> None:
    router = vending_routes(Router())
    snapshot = vending_bench.fetch(router.fetcher(), NOW)
    assert [str(r.url) for r in router.requests] == [VENDING_URL]
    assert snapshot.site == "vending_bench" and len(snapshot.rows) == 12
    assert [
        (r.extra["default_rank"], r.extra["label"], f"${r.value:,.2f}") for r in snapshot.rows[:6]
    ] == VENDING
    assert snapshot.rows[-1].value < 0  # a model can end the year in debt
    assert snapshot.raw["updated"] == {"main": "2026-10-28"}  # the newest model release listed
    assert snapshot.raw["rows"][0] == ["gemini-4-carbon_unknown", pytest.approx(16484.2067)]


def test_vending_bench_names_models_as_the_epoch_boards_do() -> None:
    snapshot = vending_bench.fetch(vending_routes(Router()).fetcher(), NOW)
    by_version = {r.extra["model_version"]: r for r in snapshot.rows}
    # "Unique display name" first, as epoch.py names a model on its other boards
    carbon = by_version["gemini-4-carbon_unknown"]
    assert (carbon.model_raw, carbon.org) == ("Gemini 4 Carbon (unknown)", "Google DeepMind")
    assert carbon.extra["release_date"] == "2026-10-28"
    # neither display name: the "Model" column
    assert by_version["grok-4-20"].model_raw
    assert by_version["kimi-k2.6"].model_raw == "Kimi K2.6"
    # Andon's own name stays as the label the card prints
    assert by_version["claude-fable-5_high"].extra["label"] == "Claude Fable 5 - High"


def test_vending_bench_keeps_the_best_row_of_a_model_version() -> None:
    text = (
        "Model version,Score,Name,Organization\n"
        "m-1,100.5,M one,Lab\nm-1,250,M one again,Lab\nm-2,,Blank,Lab\nm-3,-4,M three,Lab\n"
    )
    raw, rows = vending_bench.parse(text)
    assert [(r.extra["default_rank"], r.extra["label"], r.value) for r in rows] == [
        (1, "M one again", 250.0),
        (2, "M three", -4.0),
    ]
    assert raw["updated"] == {"main": ""}


def test_vending_bench_without_the_score_column_is_a_parse_error() -> None:
    body = "Model version,Balance\nm-1,10\n"
    router = vending_routes(Router(), body=body)
    assert code_of(vending_bench.fetch, router.fetcher(), NOW) == "parse_error"


def test_vending_bench_html_instead_of_the_csv_is_drift() -> None:
    router = Router().add(VENDING_URL, reply(200, HTML_BODY, "text/html"))
    assert code_of(vending_bench.fetch, router.fetcher(), NOW) == "selector_drift"


# ---- SimpleBench -------------------------------------------------------------------------

# simple-bench.com, MCQ tab: Rank, Model, Score (AVG@5), Organization
SIMPLEBENCH = [
    ("-", "Highest Human Score*", "95.4%", None),
    ("1st", "Claude Fable 5.2", "94.9%", "Anthropic"),
    ("2nd", "Gemini 4 Carbon", "92.6%", "Google"),
    ("3rd", "Gemini 4 Argon", "91.7%", "Google"),
    ("4th", "Claude Opus 5.5", "88.4%", "Anthropic"),
    ("5th", "Claude Fable 5.1", "86.6%", "Anthropic"),
    ("6th", "GPT-6 Astra Pro", "86.5%", "OpenAI"),
    ("-", "Human Baseline*", "83.7%", None),
    ("7th", "GPT-6 Astra", "83.6%", "OpenAI"),
]


def test_simplebench_table_equals_the_sites() -> None:
    router = simplebench_routes(Router())
    snapshot = simplebench.fetch(router.fetcher(), NOW)
    assert [str(r.url) for r in router.requests] == [SIMPLEBENCH_URL]
    assert snapshot.site == "simplebench"
    assert [
        (r.extra["rank_label"], r.model_raw, f"{r.value:.1f}%", r.org) for r in snapshot.rows[:9]
    ] == SIMPLEBENCH
    assert [r.extra["position"] for r in snapshot.rows] == list(range(1, len(snapshot.rows) + 1))
    # the human reference rows are shown in place, never ranked
    humans = [r for r in snapshot.rows if r.extra.get("human")]
    assert [r.model_raw for r in humans] == ["Highest Human Score*", "Human Baseline*"]
    assert all("default_rank" not in r.extra for r in humans)
    assert [r.extra["default_rank"] for r in snapshot.rows[1:4]] == [1, 2, 3]
    assert snapshot.rows[1].extra["date_added"] == "2026-11-10"
    assert "date_added" not in snapshot.rows[-1].extra  # the oldest rows carry no date
    assert snapshot.rows[-1].extra["default_rank"] == 112
    # the board's date is its newest addition; the open-ended table is not read
    assert snapshot.release == snapshot.raw["updated"]["mcq"] >= "2026-11-10"
    assert not [r for r in snapshot.rows if r.model_raw == "Gemini 3.1 Pro Preview"]
    assert [e["model"] for e in preview(snapshot, top=2)["mcq"]] == [
        "Claude Fable 5.2",
        "Gemini 4 Carbon",
    ]


def test_simplebench_entry_it_cannot_read_is_a_parse_error() -> None:
    script = fixture_text("simplebench_leaderboard_data_20261113.js").replace(
        'score: "92.6%"', "score: 92.6", 1
    )
    router = simplebench_routes(Router(), body=script)
    assert code_of(simplebench.fetch, router.fetcher(), NOW) == "parse_error"


def test_simplebench_script_without_the_table_is_drift() -> None:
    router = simplebench_routes(Router(), body="const somethingElse = [];\n")
    assert code_of(simplebench.fetch, router.fetcher(), NOW) == "selector_drift"
    page = Router().add(SIMPLEBENCH_URL, reply(200, HTML_BODY, "text/html"))
    assert code_of(simplebench.fetch, page.fetcher(), NOW) == "selector_drift"


# ---- ForecastBench -----------------------------------------------------------------------

# forecastbench.org/leaderboards/, Tournament, anonymous teams hidden: Rank, Org, Model,
# Dataset (N), Market (N), Overall (N), Overall 95% CI, Supers > Forecaster?
FORECASTBENCH = [
    (3, "Google DeepMind", "fire hedgehog", "65.1 (723)", "72.5 (140)", "68.6 (863)", "No"),
    (4, "NeuroFusion", "ensemble 1", "65.8 (485)", "71.3 (114)", "68.5 (599)", "No"),
    (4, "NeuroFusion", "ensemble 3", "65.9 (485)", "71.3 (114)", "68.5 (599)", "No"),
    (6, "Google DeepMind", "blue croc", "65.2 (723)", "71.8 (140)", "68.3 (863)", "No"),
]


def _cell(row: ScoreRow, score: str, count: str) -> str:
    return f"{row.extra[score]:.1f} ({row.extra[count]:,.0f})"


def test_forecastbench_default_table_equals_the_sites() -> None:
    router = forecastbench_routes(Router())
    snapshot = forecastbench.fetch(router.fetcher(), NOW)
    assert [str(r.url) for r in router.requests] == [FORECASTBENCH_URL]
    assert (snapshot.site, snapshot.release) == ("forecastbench", "2026-11-11")
    assert snapshot.raw["updated"] == {"tournament": "2026-11-11"}
    shown = [r for r in snapshot.rows if "default_rank" in r.extra]
    assert [
        (
            r.extra["default_rank"],
            r.org,
            r.model_raw,
            _cell(r, "dataset", "n_dataset"),
            _cell(r, "market", "n_market"),
            f"{r.value:.1f} ({r.extra['n']:,.0f})",
            r.extra["supers_beat"],
        )
        for r in shown[:4]
    ] == FORECASTBENCH
    fire = shown[0]
    assert (fire.ci_low, fire.ci_high, fire.metric) == (67.4, 69.9, "overall")
    assert fire.extra["entry"] == "Google DeepMind/fire hedgehog"
    # anonymous teams are in the file (ranks 1 and 2) but not in the table the page opens on
    hidden = [r for r in snapshot.rows if r.extra.get("anonymous")]
    assert [r.extra["site_rank"] for r in hidden[:2]] == [1, 2]
    assert all("default_rank" not in r.extra for r in hidden)
    medians = [r.model_raw for r in shown if "median forecast" in r.model_raw]
    assert medians == ["Superforecaster median forecast"]


def test_forecastbench_reads_a_json_array_too() -> None:
    row = {"Rank": 1, "Model": "m", "Overall": 60.5, "Team Name": "T", "Overall 95% CI": "n/a"}
    script = f"const data = {json.dumps([row])};\n const isTournament = true;"
    raw, rows = forecastbench.parse(script)
    assert [(r.model_raw, r.value, r.ci_low, r.extra["default_rank"]) for r in rows] == [
        ("m", 60.5, None, 1)
    ]
    assert raw["updated"] == {"tournament": ""}


def test_forecastbench_script_without_the_array_is_drift() -> None:
    router = forecastbench_routes(Router(), body="window.initLeaderboard_tournament = 1;")
    assert code_of(forecastbench.fetch, router.fetcher(), NOW) == "selector_drift"


@pytest.mark.parametrize(
    "literal",
    [
        "[{'Rank': 1, 'Model': 'm'}]",  # no Overall
        "[{'Rank': 1, 'Model': '', 'Overall': 50.0}]",
        "[__import__('os').getcwd()]",  # not a literal: never evaluated
        "[]",
    ],
)
def test_forecastbench_odd_rows_are_a_parse_error(literal: str) -> None:
    script = f"const data = {literal};\n const isTournament = true;"
    router = forecastbench_routes(Router(), body=script)
    assert code_of(forecastbench.fetch, router.fetcher(), NOW) == "parse_error"


# ---- with the database -------------------------------------------------------------------


def _next_day(session: Session, sites: list[str]) -> None:
    """Every board of `sites` again a day later with its default order reversed."""
    for snapshot in session.scalars(
        select(BenchmarkSnapshot).where(BenchmarkSnapshot.site.in_(sites))
    ).all():
        clone = BenchmarkSnapshot(
            site=snapshot.site,
            release=snapshot.release,
            fetched_at=NOW + timedelta(days=1),
            sha256=f"next-{snapshot.site}",
            raw={},
        )
        session.add(clone)
        session.flush()
        for score in session.scalars(
            select(BenchmarkScore).where(BenchmarkScore.snapshot_id == snapshot.id)
        ).all():
            extra = dict(score.extra)
            if "default_rank" in extra:
                extra["default_rank"] = 1000 - extra["default_rank"]
            session.add(
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
    session.flush()


@pytest.mark.db
def test_new_sites_are_served_as_their_default_views(db_session: Session) -> None:
    result = collect_all(db_session, all_sites().fetcher(), NOW)
    new = ["seal", "vals", "vending_bench", "simplebench", "forecastbench"]
    assert {site: result[site] for site in new} == dict.fromkeys(new, "saved")
    sites = {s.site: s for s in benchmarks_view(db_session, now=NOW + timedelta(hours=1))}
    assert list(sites)[-5:] == new
    assert sites["seal"].title == "Scale SEAL" and sites["vals"].license == "CC BY 4.0"
    assert sites["forecastbench"].license == "CC BY-SA 4.0"
    assert sites["simplebench"].license == "명시 없음"
    assert sites["vals"].updated == {"vals_index": "2026-11-11"}
    # the summary ranks the rows each site's table opens on, in its order
    simple = [(r.rank, r.model) for r in sites["simplebench"].rows[:2]]
    assert simple == [(1, "Claude Fable 5.2"), (2, "Gemini 4 Carbon")]
    forecast = benchmarks_view(db_session, now=NOW + timedelta(hours=1), site="forecastbench")[0]
    ranked = [r for r in forecast.rows if r.rank is not None]
    assert ranked[0].model == "fire hedgehog" and ranked[0].extra["default_rank"] == 3
    assert "model-4" in {r.model for r in forecast.rows if r.rank is None}  # an anonymous team


@pytest.mark.db
def test_spotlight_hears_the_new_sites_named_boards_only(db_session: Session) -> None:
    """SEAL's HLE, MCP Atlas and SWE-Bench Pro boards, the Vals Index, Vending-Bench 2 and
    SimpleBench take part in the leaderboard moves; ForecastBench does not."""
    collect_all(db_session, all_sites().fetcher(), NOW)
    _next_day(db_session, ["seal", "vals", "vending_bench", "simplebench", "forecastbench"])
    changes = benchmark_changes(db_session, now=NOW + timedelta(days=1, hours=1))
    boards = {(c["site"], c["board"]) for c in changes["changes"] + changes["new_models"]}
    assert boards == {
        ("Scale SEAL", "hle-diamond"),
        ("Scale SEAL", "mcp_atlas"),
        ("Scale SEAL", "swe_bench_pro_public_v2:full"),
        ("Scale SEAL", "swe_bench_pro_public_v2:hard"),
        ("Vals Index", "vals_index"),
        ("Vending-Bench 2", "main"),
        ("SimpleBench", "mcq"),
    }
    # an entry reads as the site names it: Andon's own name on Vending-Bench
    vending = {c["model"] for c in changes["changes"] if c["site"] == "Vending-Bench 2"}
    assert "Gemini 4 Carbon" in vending and "Gemini 4 Carbon (unknown)" not in vending
    # SimpleBench's human reference rows are never a "model that moved"
    assert not [c for c in changes["changes"] if "Human" in c["model"]]
