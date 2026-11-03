import copy
import json
from datetime import UTC, datetime

import httpx
import pytest

from news_insight.benchmarks.sources import (
    BenchmarkError,
    artificial_analysis,
    deepswe,
    livebench,
    lmarena,
)
from tests.benchmarks.fakes import (
    HOME_HTML,
    HTML_BODY,
    Router,
    artificial_analysis_routes,
    deepswe_routes,
    fixture_json,
    fixture_text,
    livebench_routes,
    lmarena_routes,
    reply,
)

NOW = datetime(2026, 11, 3, 3, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCE_SECRET_ARTIFICIAL_ANALYSIS_KEY", raising=False)
    monkeypatch.setattr(lmarena, "RETRY_DELAY_SECONDS", 0.0)


def test_deepswe_rows() -> None:
    snapshot = deepswe.fetch(deepswe_routes(Router()).fetcher(), NOW)
    assert snapshot.site == deepswe.SITE
    assert snapshot.release == "2026-06-20"
    assert snapshot.raw["n_tasks_in_set"] == 113
    first = snapshot.rows[0]
    assert (first.board, first.model_raw, first.metric) == ("v1.1", "gpt-5-5", "pass_at_1")
    assert first.config == "xhigh"
    assert first.ci_low is not None and first.ci_high is not None
    assert first.ci_low < first.value < first.ci_high
    # the chart axes: cost, output tokens, steps stay on the row
    assert first.extra["mean_cost_usd"] == pytest.approx(6.6058613)
    assert first.extra["mean_agent_steps"] > 0
    assert first.extra["harness"] == "mini-swe-agent"
    assert "pass_at_1" not in first.extra and "model" not in first.extra
    # a model run without a reasoning effort has no config (and no null fields in extra)
    default = snapshot.rows[-1]
    assert default.model_raw == "kimi-k2-6" and default.config is None
    assert None not in default.extra.values() and "reasoning_effort" not in default.extra


def test_livebench_picks_newest_available_release() -> None:
    router = Router()
    livebench_routes(router)
    # the bundle also lists a date whose data is not published yet
    router.routes.insert(
        0,
        (
            "livebench.ai/static/js/main",
            lambda _r: reply(
                200,
                'x=["20261030","20261025","20261014"],y="2026-06-25"',
                "application/javascript",
            ),
        ),
    )
    snapshot = livebench.fetch(router.fetcher(), NOW)
    assert snapshot.release == "2026-10-25"
    probed = [str(r.url) for r in router.requests if r.url.path.endswith("table.csv")]
    assert probed == [
        "https://livebench.ai/data/20261030/table.csv",
        "https://livebench.ai/data/20261025/table.csv",
    ]


def test_livebench_columns_become_metrics() -> None:
    snapshot = livebench.fetch(livebench_routes(Router()).fetcher(), NOW)
    scores = {(r.model_raw, r.metric): r for r in snapshot.rows if r.metric != "cost_per_success"}
    assert scores[("claude-fable-5.1", "coding")].value == 97.7
    assert {m for (_, m) in scores} == {
        "long_agentic",
        "reasoning",
        "coding",
        "browser",
        "data_analysis",
        "research",
        "design",
    }
    coding = scores[("claude-fable-5.1", "coding")]
    assert coding.board == "main" and coding.extra["category"] == "Coding"
    # the site's own sub-scores for the row's expansion
    assert coding.extra["parts"]
    # no overall: the site computes it in the browser, so none is stored
    assert not [r for r in snapshot.rows if r.metric == "overall"]
    assert snapshot.raw["release"] == "2026-10-25"
    assert set(snapshot.raw) >= {"table", "cost", "categories", "breakdown"}


def test_livebench_cost_rows() -> None:
    snapshot = livebench.fetch(livebench_routes(Router()).fetcher(), NOW)
    costs = [r for r in snapshot.rows if r.metric == "cost_per_success"]
    coding = next(
        r for r in costs if r.model_raw == "claude-fable-5.1" and r.extra["category"] == "Coding"
    )
    assert coding.value == pytest.approx(153.1886)
    assert coding.extra["questions"] == 29
    assert coding.extra["output_price_per_million"] == 50


def test_livebench_without_cost_still_works() -> None:
    router = Router().add("data/20261025/cost.csv", reply(404, "nope", "text/html"))
    livebench_routes(router)
    snapshot = livebench.fetch(router.fetcher(), NOW)
    assert snapshot.rows and not [r for r in snapshot.rows if r.metric == "cost_per_success"]


def test_livebench_html_table_is_drift() -> None:
    router = Router()
    # the site's SPA fallback: 200 text/html where the CSV should be
    router.add("data/20261025/table.csv", reply(200, HTML_BODY, "text/html"))
    livebench_routes(router)
    with pytest.raises(BenchmarkError) as err:
        livebench.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


def test_livebench_without_any_release_date_is_drift() -> None:
    router = Router().add("static/js/main", reply(200, "var a=1", "application/javascript"))
    router.add("=https://livebench.ai/", reply(200, HOME_HTML, "text/html"))
    with pytest.raises(BenchmarkError) as err:
        livebench.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


def paged_lmarena(pages: dict[int, list[dict]]) -> Router:
    def respond(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        assert request.url.params["length"] == "100"
        assert request.url.params["where"] == "\"category\"='overall'"
        rows = pages.get(offset, [])
        return reply(
            200,
            json.dumps({"rows": [{"row_idx": offset + i, "row": r} for i, r in enumerate(rows)]}),
            "application/json",
        )

    return Router().add("datasets-server.huggingface.co/filter", respond)


def test_lmarena_pages_until_empty() -> None:
    template = fixture_json("lmarena_text_style_control.json")["rows"][0]["row"]
    page1 = [{**template, "model_name": f"Model {i} (High)", "rank": i} for i in range(100)]
    page2 = [{**template, "model_name": f"Model {i}", "rank": i} for i in range(100, 105)]
    router = paged_lmarena({0: page1, 100: page2})
    snapshot = lmarena.fetch(router.fetcher(), NOW)
    boards = {r.board for r in snapshot.rows}
    assert boards == {
        "text_style_control",
        "webdev",
        "vision_style_control",
        "search_style_control",
        "agent",
    }
    assert len([r for r in snapshot.rows if r.board == "webdev"]) == 105
    first = snapshot.rows[0]
    assert first.metric == "rating" and first.extra["vote_count"] == 4403.0
    assert first.extra["rank"] == 0 and first.extra["license"] == "Proprietary"
    assert first.extra["variance"] == pytest.approx(23.0453445)
    assert first.extra["leaderboard_publish_date"] == "2026-10-28"
    assert snapshot.release == "2026-10-28"
    # a full page asks for the next one; the short one ends the board
    offsets = [int(r.url.params["offset"]) for r in router.requests if "config=agent" in str(r.url)]
    assert offsets == [0, 100]


def test_lmarena_row_fields() -> None:
    snapshot = lmarena.fetch(lmarena_routes(Router()).fetcher(), NOW)
    first = snapshot.rows[0]
    assert (first.model_raw, first.org, first.config) == (
        "Gemini 4 Carbon (High)",
        "google",
        "High",
    )
    assert first.ci_low < first.value < first.ci_high
    assert first.value == pytest.approx(1527.5065447)
    assert snapshot.rows[-1].config is not None or snapshot.rows[-1].model_raw


def test_lmarena_agent_board_reports_a_score() -> None:
    agent = fixture_text("lmarena_agent.json")
    router = Router().add("config=agent", reply(200, agent, "application/json"))
    lmarena_routes(router)
    snapshot = lmarena.fetch(router.fetcher(), NOW)
    rows = [r for r in snapshot.rows if r.board == "agent"]
    assert len(rows) == 3 and {r.metric for r in rows} == {"score"}
    top = rows[0]
    assert top.value == pytest.approx(0.2003566) and top.ci_low < top.value < top.ci_high
    assert top.extra["cost_per_task_p50"] > 0 and top.extra["session_count"] > 0
    assert top.extra["rank"] == 1 and top.config == "Max"


def test_lmarena_board_with_unknown_columns_is_drift() -> None:
    body = json.dumps({"rows": [{"row": {"model_name": "A", "points": 1.0}}]})
    router = Router().add("config=agent", reply(200, body, "application/json"))
    lmarena_routes(router)
    with pytest.raises(BenchmarkError) as err:
        lmarena.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


def test_lmarena_empty_board_is_drift() -> None:
    with pytest.raises(BenchmarkError) as err:
        lmarena.fetch(paged_lmarena({}).fetcher(), NOW)
    assert err.value.code == "selector_drift"


def test_lmarena_server_error_is_http_error_after_retries() -> None:
    router = Router().add(
        "datasets-server",
        reply(500, '{"error":"the dataset index is loading"}', "application/json"),
    )
    with pytest.raises(BenchmarkError) as err:
        lmarena.fetch(router.fetcher(), NOW)
    assert err.value.code == "http_error"
    assert len(router.requests) == lmarena.ATTEMPTS


def test_artificial_analysis_without_key_is_config_error() -> None:
    router = artificial_analysis_routes(Router())
    with pytest.raises(BenchmarkError) as err:
        artificial_analysis.fetch(router.fetcher(), NOW)
    assert err.value.code == "config_error"
    assert router.requests == []


def test_artificial_analysis_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_SECRET_ARTIFICIAL_ANALYSIS_KEY", "test-key")
    snapshot = artificial_analysis.fetch(artificial_analysis_routes(Router()).fetcher(), NOW)
    by_metric = {r.metric: r for r in snapshot.rows}
    index = by_metric["artificial_analysis_intelligence_index"]
    assert (index.model_raw, index.org, index.config, index.board) == (
        "GLM-5.3 (Max)",
        "Z AI",
        "Max",
        "language",
    )
    assert index.value == 31.7
    assert by_metric["price_1m_input_tokens"].value == 1.4
    assert by_metric["median_output_tokens_per_second"].value == 80.07
    assert "artificial_analysis_coding_index" not in by_metric  # null = not measured
    assert index.extra["slug"] == "glm-5-3" and index.extra["release_date"] == "2026-08-18"
    assert index.extra["context_window_tokens"] == 1000000
    assert snapshot.release == "v5"


def test_artificial_analysis_follows_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_SECRET_ARTIFICIAL_ANALYSIS_KEY", "test-key")
    body = fixture_json("artificial_analysis.json")

    def respond(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        data = copy.deepcopy(body)
        data["data"][0]["name"] = f"Model {page}"
        data["pagination"] = {"page": page, "total_pages": 2, "has_more": page < 2}
        return reply(200, json.dumps(data), "application/json")

    router = Router().add("artificialanalysis.ai/api/v2/language/models", respond)
    snapshot = artificial_analysis.fetch(router.fetcher(), NOW)
    assert {r.model_raw for r in snapshot.rows} == {"Model 1", "Model 2"}
    assert len(snapshot.raw["data"]) == 2


@pytest.mark.parametrize("site", ["deepswe", "lmarena", "artificial_analysis"])
def test_html_instead_of_json_is_drift(site: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_SECRET_ARTIFICIAL_ANALYSIS_KEY", "test-key")
    router = Router().add("", reply(200, HTML_BODY, "text/html"))
    module = {"deepswe": deepswe, "lmarena": lmarena, "artificial_analysis": artificial_analysis}[
        site
    ]
    with pytest.raises(BenchmarkError) as err:
        module.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


def test_json_without_rows_is_drift() -> None:
    router = Router().add("deepswe", reply(200, '{"scope": "moved"}', "application/json"))
    with pytest.raises(BenchmarkError) as err:
        deepswe.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


def test_http_failure_is_http_error() -> None:
    router = Router().add("deepswe", reply(503, "down", "text/plain"))
    with pytest.raises(BenchmarkError) as err:
        deepswe.fetch(router.fetcher(), NOW)
    assert err.value.code == "http_error"


def test_every_site_names_itself() -> None:
    for module in (deepswe, livebench, lmarena, artificial_analysis):
        assert module.SITE and module.TITLE and module.SOURCE_URL.startswith("https://")
        assert module.LICENSE and module.ATTRIBUTION
    assert fixture_text("deepswe.json")


def test_daily_job_is_scheduled_at_0330() -> None:
    from celery.schedules import crontab

    from news_insight.jobs import tasks  # noqa: F401 - registers the task
    from news_insight.jobs.celery_app import BEAT_SCHEDULE, celery_app

    entry = BEAT_SCHEDULE["benchmarks-collect"]
    assert entry["task"] == "benchmarks.collect"
    assert entry["schedule"] == crontab(hour=3, minute=30)
    assert "benchmarks.collect" in celery_app.tasks
