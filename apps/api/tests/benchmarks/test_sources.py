import copy
import io
import json
from datetime import UTC, date, datetime

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from news_insight.benchmarks.sources import (
    BenchmarkError,
    artificial_analysis,
    deepswe,
    livebench,
    lmarena,
)
from tests.benchmarks.fakes import (
    FIXTURES,
    HOME_HTML,
    HTML_BODY,
    FakeClock,
    Responder,
    Router,
    artificial_analysis_routes,
    deepswe_routes,
    fixture_json,
    fixture_text,
    livebench_routes,
    lmarena_routes,
    parquet_url,
    reply,
)

NOW = datetime(2026, 11, 3, 3, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    monkeypatch.delenv("SOURCE_SECRET_ARTIFICIAL_ANALYSIS_KEY", raising=False)
    fake = FakeClock()
    monkeypatch.setattr(lmarena, "_sleep", fake.sleep)
    return fake


def test_deepswe_stores_both_boards() -> None:
    router = deepswe_routes(Router())
    snapshot = deepswe.fetch(router.fetcher(), NOW)
    assert snapshot.site == deepswe.SITE
    assert [str(r.url) for r in router.requests] == [
        "https://deepswe.datacurve.ai/artifacts/v1.1/leaderboard-live.json",
        "https://deepswe.datacurve.ai/artifacts/v1/leaderboard-live.json",
        "https://deepswe.datacurve.ai/",
        "https://deepswe.datacurve.ai/assets/live-leaderboard-CCyhM4yo.js",
        "https://deepswe.datacurve.ai/assets/index-DYZDg9jy.js",
    ]
    assert snapshot.release == "2026-09-22"  # the newest file
    assert set(snapshot.raw["boards"]) == {"v1.1", "v1"}
    assert snapshot.raw["updated"] == {"v1.1": "2026-09-22", "v1": "2026-06-20"}
    assert snapshot.raw["boards"]["v1.1"]["n_tasks_in_set"] == 113
    assert [r.board for r in snapshot.rows] == ["v1.1"] * 3 + ["v1"] * 3
    first = snapshot.rows[0]
    assert (first.model_raw, first.metric) == ("gpt-6-astra", "pass_at_1")
    assert first.config == "xhigh" and first.org == "openai"
    assert first.value == pytest.approx(0.7411504)
    assert first.ci_low is not None and first.ci_high is not None
    assert first.ci_low < first.value < first.ci_high
    # the chart axes: cost, output tokens, steps stay on the row; the provider too
    assert first.extra["mean_cost_usd"] == pytest.approx(4.4291172)
    assert first.extra["mean_agent_steps"] > 0
    assert first.extra["harness"] == "mini-swe-agent" and first.extra["provider"] == "openai"
    assert first.extra["cost_basis"].startswith("Current pricing")
    assert "pass_at_1" not in first.extra and "model" not in first.extra
    # the cost the site's table shows for claude-opus-5 max
    opus = snapshot.rows[1]
    assert opus.model_raw == "claude-opus-5" and opus.org is None
    assert opus.extra["mean_cost_usd"] == pytest.approx(11.8375833)
    # a model run without a reasoning effort has no config (and no null fields in extra)
    default = snapshot.rows[2]
    assert default.model_raw == "kimi-k2-7-code" and default.config is None
    assert None not in default.extra.values() and "reasoning_effort" not in default.extra
    v1 = [r for r in snapshot.rows if r.board == "v1"]
    assert v1[0].model_raw == "gpt-5-5" and v1[0].config == "xhigh"
    assert v1[0].extra["mean_cost_usd"] == pytest.approx(6.6058613)


@pytest.mark.parametrize("board", ["v1.1", "v1"])
def test_deepswe_either_board_failing_fails_the_site(board: str) -> None:
    router = Router()
    path = "artifacts/v1.1/" if board == "v1.1" else "artifacts/v1/"
    router.add(path, reply(503, "down", "text/plain"))
    deepswe_routes(router)
    with pytest.raises(BenchmarkError) as err:
        deepswe.fetch(router.fetcher(), NOW)
    assert err.value.code == "http_error"


@pytest.mark.parametrize("board", ["v1.1", "v1"])
@pytest.mark.parametrize(
    "body",
    [
        pytest.param('{"scope": "moved"}', id="no-rows"),
        pytest.param('{"rows": [{"model": "m", "pass_at_1": null}]}', id="no-usable-rows"),
        pytest.param("not json", id="not-json"),
    ],
)
def test_deepswe_unreadable_board_is_drift(board: str, body: str) -> None:
    router = Router()
    path = "artifacts/v1.1/" if board == "v1.1" else "artifacts/v1/"
    router.add(path, reply(200, body, "application/json"))
    deepswe_routes(router)
    with pytest.raises(BenchmarkError) as err:
        deepswe.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


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


def test_livebench_rows_carry_the_models_metadata() -> None:
    snapshot = livebench.fetch(livebench_routes(Router()).fetcher(), NOW)
    scores = [r for r in snapshot.rows if r.metric == "coding"]
    by_model = {r.model_raw: r for r in scores}
    closed = by_model["claude-fable-5.1"]
    assert closed.org == "Anthropic"
    assert closed.extra["display_name"] == "Claude Fable 5.1"
    assert closed.extra["organization"] == "Anthropic"
    assert closed.extra["open_weights"] is False
    open_model = by_model["deepseek-v4.1-flash-1017"]
    assert open_model.org == "DeepSeek" and open_model.extra["open_weights"] is True
    # absent from the bundle: unknown, neither closed nor open
    missing = by_model["claude-sonnet-5.5"]
    assert missing.org is None
    assert not {"display_name", "organization", "open_weights"} & set(missing.extra)
    # the cost rows of a model name its maker too
    cost = next(
        r
        for r in snapshot.rows
        if r.metric == "cost_per_success" and r.model_raw == "claude-opus-5.5"
    )
    assert cost.org == "Anthropic"


def test_livebench_metadata_from_the_bundle() -> None:
    bundle = fixture_text("livebench_main.js")
    found = livebench.model_metadata(bundle)
    assert found["claude-opus-5.5"] == {
        "display_name": "Claude Opus 5.5",
        "organization": "Anthropic",
        "open_weights": False,
    }
    assert found["deepseek-v4.1-flash-1017"]["open_weights"] is True
    assert "claude-sonnet-5.5" not in found
    # a base entry's variants are models of their own that inherit its maker and licence
    assert found["gpt-5-high"] == {
        "display_name": "GPT-5 High",
        "organization": "OpenAI",
        "open_weights": False,
        "base_name": "gpt-5",
    }
    assert found["gpt-5"]["display_name"] == "GPT-5"


def test_livebench_metadata_variant_may_override_and_strings_may_hold_braces() -> None:
    bundle = (
        'const gn={"a":{displayName:"A {beta} \\"x\\"",organization:"Lab",openweight:!1,'
        'variants:[{rawName:"a-open",openweight:!0},{rawName:"a-named",displayName:"Named",'
        'organization:"Other"}]},b:{organization:"NoName"}};'
    )
    found = livebench.model_metadata(bundle)
    assert found["a"]["display_name"] == 'A {beta} "x"'
    assert found["a-open"] == {**found["a"], "open_weights": True, "base_name": "a"}
    assert found["a-named"] == {
        "display_name": "Named",
        "organization": "Other",
        "open_weights": False,
        "base_name": "a",
    }
    assert "b" not in found  # an object without a displayName is not a model entry


def test_livebench_without_metadata_still_works() -> None:
    router = Router()
    router.add(
        "livebench.ai/static/js/main",
        lambda _r: reply(200, 'x=["20261025"]', "application/javascript"),
    )
    livebench_routes(router)
    snapshot = livebench.fetch(router.fetcher(), NOW)
    assert snapshot.rows and all(r.org is None for r in snapshot.rows)
    assert not any("open_weights" in r.extra for r in snapshot.rows)


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


def test_livebench_html_fallback_candidate_is_skipped() -> None:
    router = Router()
    # the newest date is answered by the SPA fallback page, the next one has data
    router.add("data/20261030/table.csv", reply(200, HTML_BODY, "text/html"))
    router.routes.insert(
        0,
        (
            "livebench.ai/static/js/main",
            lambda _r: reply(200, 'x=["20261030","20261025","20261014"]', "application/javascript"),
        ),
    )
    livebench_routes(router)
    assert livebench.fetch(router.fetcher(), NOW).release == "2026-10-25"


def test_livebench_html_fallback_for_optional_files_is_ignored() -> None:
    router = Router()
    router.add("data/20261025/cost.csv", reply(200, HTML_BODY, "text/html"))
    router.add("data/20261025/breakdown.json", reply(200, HTML_BODY, "text/html"))
    livebench_routes(router)
    snapshot = livebench.fetch(router.fetcher(), NOW)
    assert snapshot.rows and snapshot.raw["cost"] == [] and snapshot.raw["breakdown"] == {}
    assert not [r for r in snapshot.rows if r.metric == "cost_per_success"]


def test_livebench_without_any_release_date_is_drift() -> None:
    router = Router().add("static/js/main", reply(200, "var a=1", "application/javascript"))
    router.add("=https://livebench.ai/", reply(200, HOME_HTML, "text/html"))
    with pytest.raises(BenchmarkError) as err:
        livebench.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


def parquet_bytes(rows: list[dict]) -> bytes:
    sink = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), sink)
    return sink.getvalue()


def board_rows(board: str) -> list[dict]:
    return pq.read_table(FIXTURES / f"lmarena_{board}.parquet").to_pylist()


def serve(router: Router, board: str, body: bytes | Responder | httpx.Response) -> None:
    """Replace one board's parquet (added first, so it wins over lmarena_routes)."""
    if isinstance(body, bytes):
        body = reply(200, body, "application/octet-stream")
    responder = body if callable(body) else (lambda _r, _x=body: _x)
    router.routes.insert(0, (f"={parquet_url(board)}", responder))


def test_lmarena_reads_each_boards_latest_parquet() -> None:
    router = lmarena_routes(Router())
    snapshot = lmarena.fetch(router.fetcher(), NOW)
    assert {r.board for r in snapshot.rows} == {
        "text_style_control",
        "webdev",
        "vision_style_control",
        "search",  # arena.ai opens search without style control
        "agent",
    }
    # five 'overall' rows per board; the text fixture also holds two other categories
    for board in lmarena.BOARDS:
        assert len([r for r in snapshot.rows if r.board == board]) == 5
    assert snapshot.release == "2026-11-02"  # the newest publish date, the agent board's
    assert snapshot.raw["updated"] == {
        "text_style_control": "2026-10-28",
        "webdev": "2026-10-28",
        "vision_style_control": "2026-10-19",
        "search": "2026-10-13",
        "agent": "2026-11-02",
    }
    assert set(snapshot.raw["boards"]) == set(lmarena.BOARDS)
    assert all(row["category"] == "overall" for row in snapshot.raw["boards"]["text_style_control"])
    # the Hub answers 302 to a CDN host, which is followed; nothing else is asked for
    urls = [str(r.url) for r in router.requests]
    assert len(urls) == 10 and all("datasets-server" not in u for u in urls)
    assert urls[0] == parquet_url("text_style_control")


def test_lmarena_row_fields() -> None:
    snapshot = lmarena.fetch(lmarena_routes(Router()).fetcher(), NOW)
    first = snapshot.rows[0]
    assert (first.model_raw, first.org, first.config) == (
        "Gemini 4 Carbon (High)",
        "google",
        "High",
    )
    assert first.metric == "rating" and first.value == pytest.approx(1527.5065447)
    assert first.ci_low < first.value < first.ci_high
    assert first.extra["vote_count"] == 4403.0 and first.extra["rank"] == 1
    assert first.extra["license"] == "Proprietary"
    assert first.extra["variance"] == pytest.approx(23.0453445)
    assert first.extra["leaderboard_publish_date"] == "2026-10-28"
    assert "category" not in first.extra and "model_name" not in first.extra
    assert {r.config for r in snapshot.rows if r.board == "text_style_control"} >= {"High"}
    assert all(r.org and r.extra["rank"] for r in snapshot.rows)


def test_lmarena_agent_board_reports_a_score() -> None:
    snapshot = lmarena.fetch(lmarena_routes(Router()).fetcher(), NOW)
    rows = [r for r in snapshot.rows if r.board == "agent"]
    assert {r.metric for r in rows} == {"score"}
    top = rows[0]
    assert top.value == pytest.approx(0.2003566) and top.ci_low < top.value < top.ci_high
    assert top.extra["cost_per_task_p50"] > 0 and top.extra["session_count"] > 0
    assert top.extra["observation_count"] > 0
    assert top.extra["rank"] == 1 and top.config == "Max"


def test_lmarena_nulls_in_a_row_are_not_stored() -> None:
    rows = board_rows("webdev")
    rows[0]["rating_lower"] = None
    rows[0]["vote_count"] = None
    router = lmarena_routes(Router())
    serve(router, "webdev", parquet_bytes(rows))
    snapshot = lmarena.fetch(router.fetcher(), NOW)
    first = next(r for r in snapshot.rows if r.board == "webdev")
    assert first.ci_low is None and "vote_count" not in first.extra


def test_lmarena_nan_is_not_a_value() -> None:
    rows = board_rows("webdev")
    rows[0]["rating"] = float("nan")
    rows[1]["variance"] = float("inf")
    router = lmarena_routes(Router())
    serve(router, "webdev", parquet_bytes(rows))
    snapshot = lmarena.fetch(router.fetcher(), NOW)
    scored = [r for r in snapshot.rows if r.board == "webdev"]
    assert len(scored) == 4 and "variance" not in scored[0].extra
    json.dumps(snapshot.raw, allow_nan=False)  # the snapshot is storable


def test_lmarena_date_values_are_stored_as_iso_text() -> None:
    rows = board_rows("webdev")
    for row in rows:  # a parquet date column comes back as datetime.date objects
        row["leaderboard_publish_date"] = date(2026, 11, 2)
    router = lmarena_routes(Router())
    serve(router, "webdev", parquet_bytes(rows))
    snapshot = lmarena.fetch(router.fetcher(), NOW)
    stored = snapshot.raw["boards"]["webdev"]
    assert {r["leaderboard_publish_date"] for r in stored} == {"2026-11-02"}
    assert snapshot.release == "2026-11-02"
    json.dumps(snapshot.raw, allow_nan=False)  # dates would not serialize


def test_lmarena_board_with_unknown_columns_is_drift() -> None:
    router = lmarena_routes(Router())
    serve(
        router, "agent", parquet_bytes([{"model_name": "A", "points": 1.0, "category": "overall"}])
    )
    with pytest.raises(BenchmarkError) as err:
        lmarena.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


def test_lmarena_board_without_overall_rows_is_drift() -> None:
    rows = [{**row, "category": "coding"} for row in board_rows("webdev")]
    router = lmarena_routes(Router())
    serve(router, "webdev", parquet_bytes(rows))
    with pytest.raises(BenchmarkError) as err:
        lmarena.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(HTML_BODY.encode(), id="login-wall"),
        pytest.param(b"PAR1 but not really a parquet file", id="garbage"),
        pytest.param(parquet_bytes([{"model_name": "A", "rating": 1.0}]), id="no-category-column"),
    ],
)
def test_lmarena_unreadable_file_is_drift(body: bytes) -> None:
    router = lmarena_routes(Router())
    serve(router, "search", body)
    with pytest.raises(BenchmarkError) as err:
        lmarena.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


def test_lmarena_html_answer_is_drift() -> None:
    router = lmarena_routes(Router())
    serve(router, "webdev", reply(200, HTML_BODY, "text/html"))
    with pytest.raises(BenchmarkError) as err:
        lmarena.fetch(router.fetcher(), NOW)
    assert err.value.code == "selector_drift"


def test_lmarena_retries_a_transient_error_once(clock: FakeClock) -> None:
    calls = {"n": 0}

    def flaky(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return reply(503, "busy", "text/plain")
        return reply(
            200, (FIXTURES / "lmarena_webdev.parquet").read_bytes(), "application/octet-stream"
        )

    router = lmarena_routes(Router())
    serve(router, "webdev", flaky)
    snapshot = lmarena.fetch(router.fetcher(), NOW)
    assert calls["n"] == 2 and clock.sleeps == [lmarena.RETRY_DELAY_SECONDS]
    assert len([r for r in snapshot.rows if r.board == "webdev"]) == 5


def test_lmarena_gives_up_after_the_retry(clock: FakeClock) -> None:
    router = lmarena_routes(Router())
    serve(router, "webdev", reply(503, "busy", "text/plain"))
    with pytest.raises(BenchmarkError) as err:
        lmarena.fetch(router.fetcher(), NOW)
    assert err.value.code == "http_error" and err.value.retryable
    assert len(clock.sleeps) == 1


def test_lmarena_missing_file_is_not_retried(clock: FakeClock) -> None:
    router = lmarena_routes(Router())
    serve(router, "webdev", reply(404, "Not found", "text/plain"))
    with pytest.raises(BenchmarkError) as err:
        lmarena.fetch(router.fetcher(), NOW)
    assert err.value.code == "http_error" and not clock.sleeps


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


def test_http_failure_is_http_error() -> None:
    router = Router().add("deepswe", reply(503, "down", "text/plain"))
    with pytest.raises(BenchmarkError) as err:
        deepswe.fetch(router.fetcher(), NOW)
    assert err.value.code == "http_error"


def test_every_site_names_itself() -> None:
    for module in (deepswe, livebench, lmarena, artificial_analysis):
        assert module.SITE and module.TITLE and module.SOURCE_URL.startswith("https://")
        assert module.LICENSE and module.ATTRIBUTION
    assert artificial_analysis.ATTRIBUTION == "Data: Artificial Analysis"
    assert fixture_text("deepswe_v1_1.json")


def test_daily_job_is_scheduled_at_0330() -> None:
    from celery.schedules import crontab

    from news_insight.jobs import tasks  # noqa: F401 - registers the task
    from news_insight.jobs.celery_app import BEAT_SCHEDULE, celery_app

    entry = BEAT_SCHEDULE["benchmarks-collect"]
    assert entry["task"] == "benchmarks.collect"
    assert entry["schedule"] == crontab(hour=3, minute=30)
    assert "benchmarks.collect" in celery_app.tasks
