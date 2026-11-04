"""The ranked boards equal what each site shows by default, on responses recorded 2026-11-04.

The expected lists were read off the sites' own pages that day (deepswe.datacurve.ai's table,
livebench.ai's leaderboard, arena.ai's text and search boards), in the precision they print.
"""

from datetime import UTC, datetime

import pytest

from news_insight.benchmarks.sources import deepswe, livebench, lmarena
from news_insight.public.benchmarks import preview
from tests.benchmarks.fakes import (
    DEEPSWE_CHUNK,
    FakeClock,
    Router,
    deepswe_routes,
    fixture_text,
    livebench_routes,
    lmarena_routes,
    reply,
)

NOW = datetime(2026, 11, 4, 3, 30, tzinfo=UTC)

# deepswe.datacurve.ai, v1.1, "Best": the table's 21 rows (Models 21/28), name [effort] pass@1
DEEPSWE_V1_1 = [
    ("gpt-6-astra", "xhigh", 74),
    ("gemini-3-8-flash", "high", 74),
    ("claude-opus-5", "max", 74),
    ("gpt-5-6-sol", "max", 73),
    ("claude-fable-5", "xhigh", 70),
    ("glm-5-3", "max", 69),
    ("kimi-k3", "max", 69),
    ("grok-4-6", "medium", 67),
    ("gpt-5-6-luna", "max", 67),
    ("gpt-5-5", "xhigh", 67),
    ("gemini-3-7-flash", "medium", 65),
    ("glm-5-3-flash", "max", 63),
    ("deepseek-v4-pro", "max", 63),
    ("claude-opus-4-8", "max", 59),
    ("qwen3-8-max", "xhigh", 57),
    ("muse-spark-1-2", "xhigh", 55),
    ("claude-sonnet-5", "max", 54),
    ("deepseek-v4-flash", "max", 53),
    ("gemini-3-6-flash", "high", 47),
    ("glm-5-2", "max", 44),
    ("gemini-3-5-flash", "high", 36),
]
# the same table on v1 (Models 15/21)
DEEPSWE_V1 = [
    ("gpt-5-5", "xhigh", 70),
    ("claude-opus-4-8", "max", 58),
    ("claude-opus-4-7", "max", 54),
    ("glm-5-2", "max", 42),
    ("gemini-3-5-flash", "medium", 28),
    ("claude-opus-4-6", "max", 28),
    ("gpt-5-4-mini", "xhigh", 24),
    ("kimi-k2-6", None, 24),
    ("minimax-m3", None, 20),
    ("mimo-v2-5-pro", None, 19),
    ("qwen3-7-max", None, 18),
    ("glm-5-1", None, 18),
    ("grok-build-0-1", None, 13),
    ("deepseek-v4-pro", None, 8),
    ("gemini-3-flash-preview", None, 5),
]
# livebench.ai, latest release (25 October 2026): model, Overall as the table prints it
LIVEBENCH = [
    ("claude-fable-5.1", 85.7),
    ("gpt-6-astra", 85.6),
    ("claude-opus-5.5", 85.1),
    ("gpt-6.1-sol", 84.1),
    ("claude-sonnet-5.5", 80.0),
    ("gemini-4-argon", 79.3),
    ("gpt-6.1-terra", 77.8),
    ("muse-wonder-1.0", 74.2),
    ("deepseek-v4.1-flash-1017", 72.9),
    ("kimi-k3.1-pro", 71.3),
    ("grok-4.7", 70.1),
    ("claude-haiku-5.5", 69.8),
    ("mimo-v2.6-pro", 68.5),
    ("gpt-5.6-terra", 67.8),
    ("grok-4.6", 67.8),
    ("minimax-m3.1-flash", 66.9),
    ("gpt-6-luna", 64.6),
    ("kimi-k3", 64.6),
    ("mistral-large-4-0", 63.5),
    ("muse-spark-1.3", 63.0),
    ("glm-5.3-flash", 62.1),
    ("qwen3.8-max", 61.6),
]
# arena.ai Text Arena, Overall, Style Control (its default): rank, model, score, votes
ARENA_TEXT = [
    (1, "Gemini 4 Carbon (High)", 1528, 4403),
    (2, "Gemini 4 Argon (High)", 1520, 11889),
    (3, "Claude Opus 5.5 (High)", 1509, 11415),
    (4, "Muse Wonder (Max)", 1507, 7749),
    (5, "Claude Fable 5.1 (Max)", 1504, 17178),
    (6, "Claude Fable 5 (High)", 1504, 45341),
    (7, "Claude Opus 4.6 (High)", 1503, 84512),
    (8, "Claude Opus 4.7 (High)", 1501, 65110),
    (9, "Claude Opus 4.6", 1496, 89324),
    (10, "Gemini 3.8 Flash (High)", 1496, 47803),
    (11, "Muse Spark 1.3 (Max)", 1495, 22134),
    (12, "Claude Opus 4.7", 1494, 66140),
    (13, "Muse Spark 1.2 (xHigh)", 1492, 11724),
    (14, "Claude Opus 5 (High)", 1492, 73167),
    (15, "Claude Opus 5 (Max)", 1491, 35531),
    (16, "Muse Spark 1.1", 1490, 46354),
    (17, "Gemini 3.7 Flash (High)", 1490, 32289),
    (18, "Muse Spark", 1489, 14140),
    (19, "Kimi K3 (Max)", 1488, 36780),
    (20, "Gemini 3.1 Pro Preview", 1487, 132547),
]
# arena.ai Search Arena (opens without style control): rank, score, votes (the page prints
# display names; the dataset has the ids, matched here by votes)
ARENA_SEARCH = [
    (1, "gpt-5.6-sol-xhigh", 1261, 60437),
    (2, "qwen3.8-max", 1261, 1870),
    (3, "claude-opus-4-6-search", 1251, 173191),
    (4, "gpt-5.5-search", 1247, 125957),
    (5, "claude-fable-5.1-high", 1246, 12782),
    (6, "claude-opus-5-high", 1242, 13285),
    (7, "gpt-6-astra-max", 1234, 18483),
    (8, "gpt-6.1-sol-max", 1233, 5555),
    (9, "claude-opus-4-7", 1230, 127506),
    (10, "claude-fable-5-high", 1229, 73596),
    (11, "ernie-5.1", 1227, 4024),
]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lmarena, "_sleep", FakeClock().sleep)


def test_deepswe_default_table_equals_the_sites() -> None:
    router = deepswe_routes(Router(), recorded=True)
    snapshot = deepswe.fetch(router.fetcher(), NOW)
    assert snapshot.raw["default_view"] == {
        "min_best": 0.05,
        "hidden": sorted(deepswe.DEFAULT_HIDDEN),
    }
    boards = preview(snapshot, top=100)
    for board, expected in (("v1.1", DEEPSWE_V1_1), ("v1", DEEPSWE_V1)):
        shown = [(e["model"], e["config"], round(e["value"] * 100)) for e in boards[board]]
        assert shown == expected, board
    assert snapshot.raw["updated"] == {"v1.1": "2026-09-22", "v1": "2026-06-20"}


# the same table's "Avg cost" column: the page re-prices these models at today's prices
DEEPSWE_COSTS = {
    ("v1.1", "gpt-5-6-luna", "max"): "$0.61",
    ("v1.1", "gpt-5-6-sol", "max"): "$6.46",
    ("v1.1", "glm-5-3-flash", "max"): "$0.24",
    ("v1.1", "deepseek-v4-pro", "max"): "$1.67",
    ("v1.1", "deepseek-v4-flash", "max"): "$0.46",
    ("v1.1", "gemini-3-6-flash", "high"): "$2.21",
    ("v1.1", "claude-opus-5", "max"): "$11.84",  # not in the table: as served
    ("v1.1", "gpt-6-astra", "xhigh"): "$4.43",
    ("v1", "deepseek-v4-pro", None): "$1.05",  # the v1 board has its own price pair
    ("v1", "gpt-5-5", "xhigh"): "$6.61",
}


def test_deepswe_costs_are_repriced_like_the_site() -> None:
    snapshot = deepswe.fetch(deepswe_routes(Router(), recorded=True).fetcher(), NOW)
    assert snapshot.raw["repricing"] == deepswe.DEFAULT_REPRICING
    cost = {
        (r.board, r.model_raw, r.config): f"${r.extra['mean_cost_usd']:.2f}" for r in snapshot.rows
    }
    for key, shown in DEEPSWE_COSTS.items():
        assert cost[key] == shown, key
    # the stored board stays as the site serves it
    luna = next(
        r
        for r in snapshot.raw["boards"]["v1.1"]["rows"]
        if r["model"] == "gpt-5-6-luna" and r.get("reasoning_effort") == "max"
    )
    assert f"${luna['mean_cost_usd']:.2f}" == "$3.03"


def test_deepswe_chart_opens_on_the_sites_57_configurations() -> None:
    # "Configs (57/70)": the default models' configurations at $15 a task or less
    snapshot = deepswe.fetch(deepswe_routes(Router(), recorded=True).fetcher(), NOW)
    shown = {e["model"] for e in preview(snapshot, top=100)["v1.1"]}
    rows = [r for r in snapshot.rows if r.board == "v1.1"]
    assert len(rows) == 70
    assert sum(1 for r in rows if r.model_raw in shown and r.extra["mean_cost_usd"] <= 15) == 57


def test_deepswe_repricing_table_read_from_the_main_script() -> None:
    script = (
        'x=1,T={"m-1":{from:{input:2,cached:.5,output:10},to:{input:1,cached:.25,output:5}}},'
        "R=/(^|_)cost_usd$/,"
    )
    table = deepswe.repricing(script)
    assert table == {
        "m-1": {
            "from": {"input": 2, "cached": 0.5, "output": 10},
            "to": {"input": 1, "cached": 0.25, "output": 5},
        }
    }
    row = {"model": "m.1", "mean_cost_usd": 4.0, "total_cost_usd": 8.0, "mean_output_tokens": 10.0}
    # no input tokens: one factor across the board (all prices halved) is still applied
    assert deepswe.repriced(row, "v1.1", table)["mean_cost_usd"] == 2.0
    assert deepswe.repriced({"model": "other", "mean_cost_usd": 4.0}, "v1.1", table) == {
        "model": "other",
        "mean_cost_usd": 4.0,
    }
    assert deepswe.repricing("no table") is None


def test_deepswe_hidden_models_are_not_ranked() -> None:
    snapshot = deepswe.fetch(deepswe_routes(Router(), recorded=True).fetcher(), NOW)
    ranked = {e["model"] for board in preview(snapshot, top=100).values() for e in board}
    # all stored, none ranked: the site keeps them out of its default chart and table
    stored = {r.model_raw for r in snapshot.rows}
    assert {"gpt-5-6-terra", "gpt-5-4", "claude-sonnet-4-6"} <= stored
    assert not ranked & set(deepswe.DEFAULT_HIDDEN)


def test_deepswe_defaults_read_from_the_page_script() -> None:
    chunk = 'x=1;const q=.1,w=new Set(["a","b"]),z=2;'
    assert deepswe.default_view(chunk) == {"min_best": 0.1, "hidden": ["a", "b"]}
    assert deepswe.default_view("no defaults here") is None
    router = Router().add(f"={DEEPSWE_CHUNK}", reply(200, chunk, "application/javascript"))
    snapshot = deepswe.fetch(deepswe_routes(router).fetcher(), NOW)
    assert snapshot.raw["default_view"] == {"min_best": 0.1, "hidden": ["a", "b"]}


@pytest.mark.parametrize(
    "page",
    [
        pytest.param(reply(503, "down", "text/plain"), id="page-down"),
        pytest.param(reply(200, "<html>no script</html>", "text/html"), id="no-script"),
    ],
)
def test_deepswe_unreadable_page_falls_back_to_the_last_known_defaults(page: object) -> None:
    router = Router().add("=https://deepswe.datacurve.ai/", page)  # type: ignore[arg-type]
    snapshot = deepswe.fetch(deepswe_routes(router).fetcher(), NOW)
    assert snapshot.raw["default_view"] == deepswe.fallback_view()
    assert snapshot.raw["repricing"] == deepswe.DEFAULT_REPRICING
    assert len(snapshot.rows) == 6  # the boards are unaffected


def test_livebench_default_table_equals_the_sites() -> None:
    router = livebench_routes(Router(), recorded=True)
    snapshot = livebench.fetch(router.fetcher(), NOW)
    board = preview(snapshot, top=100)["main"]
    assert len(board) == 32  # every model of the release, as the site lists them
    shown = [(e["model"], round(e["value"], 1)) for e in board[: len(LIVEBENCH)]]
    assert shown == LIVEBENCH
    assert snapshot.raw["updated"] == {"main": "2026-10-25"}


def test_livebench_model_missing_from_the_script_is_not_ranked() -> None:
    table = fixture_text("livebench_table_20261025.csv") + "mystery-model,99,99,99,99,99,99,99\n"
    router = livebench_routes(Router(), recorded=True, table=table)
    snapshot = livebench.fetch(router.fetcher(), NOW)
    mystery = [r for r in snapshot.rows if r.model_raw == "mystery-model"]
    assert mystery and all(r.extra["listed"] is False for r in mystery)
    board = preview(snapshot, top=100)["main"]
    assert board[0]["model"] == "claude-fable-5.1" and len(board) == 32


def test_lmarena_text_board_equals_the_sites() -> None:
    snapshot = lmarena.fetch(lmarena_routes(Router(), recorded=True).fetcher(), NOW)
    board = preview(snapshot, top=20)["text_style_control"]
    shown = [(e["rank"], e["model"], round(e["value"]), int(e["votes"])) for e in board]
    assert shown == ARENA_TEXT
    assert all(e["rank"] == e["site_rank"] for e in board)
    assert snapshot.raw["updated"]["text_style_control"] == "2026-10-28"


def test_lmarena_search_board_is_the_sites_default_without_style_control() -> None:
    snapshot = lmarena.fetch(lmarena_routes(Router(), recorded=True).fetcher(), NOW)
    board = preview(snapshot, top=11)["search"]
    shown = [(e["rank"], e["model"], round(e["value"]), int(e["votes"])) for e in board]
    assert shown == ARENA_SEARCH
    assert "search_style_control" not in snapshot.raw["boards"]
