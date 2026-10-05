from datetime import UTC, datetime, timedelta

from news_insight.ops.logreport import analyse, parse_lines, render, signature

T0 = datetime(2026, 10, 5, 3, 20, tzinfo=UTC)


def stamp(offset_s: int) -> str:
    return (T0 + timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%S.000000000Z")


UVICORN_TRACE = [
    f"{stamp(0)} ERROR:    Exception in ASGI application",
    f"{stamp(0)} Traceback (most recent call last):",
    f'{stamp(0)}   File "/opt/venv/lib/python3.12/site-packages/psycopg/cursor.py", line 117, in execute',
    f"{stamp(0)} psycopg.OperationalError: sending query and params failed: number of parameters must be between 0 and 65535",
    f"{stamp(0)} The above exception was the direct cause of the following exception:",
    f"{stamp(0)} sqlalchemy.exc.OperationalError: (psycopg.OperationalError) sending query and params failed: number of parameters must be between 0 and 65535",
    f"{stamp(0)} [SQL: SELECT keyword_labels.key, keyword_labels.label ",
    f"{stamp(0)} FROM keyword_labels ",
    f"{stamp(0)} WHERE keyword_labels.key IN (%(key_1_1)s::VARCHAR)]",
    f"{stamp(0)} [parameters: {{'key_1_1': 'x'}}]",
    f"{stamp(0)} (Background on this error at: https://sqlalche.me/e/20/e3q8)",
    f'{stamp(1)} {{"ts": "{T0.isoformat()}", "level": "info", "service": "api", "logger": "news_insight.http", "msg": "request", "method": "GET", "path": "/api/public/insights", "status": 500, "ms": 4650}}',
]


def test_a_traceback_is_one_event_named_by_its_last_exception() -> None:
    events = list(parse_lines("api", UVICORN_TRACE))
    errors = [e for e in events if e.level == "error"]
    assert len(errors) == 1
    assert errors[0].message.startswith("sqlalchemy.exc.OperationalError")
    assert errors[0].ts == T0
    assert events[-1].data["status"] == 500


def test_signatures_hide_what_varies_but_keep_constraint_names() -> None:
    a = signature(
        '2026-10-05 02:19:54.216 UTC [11107] ERROR:  duplicate key value violates unique constraint "pk_item_lsh"'
    )
    b = signature(
        '2026-10-05 03:18:01.002 UTC [16000] ERROR:  duplicate key value violates unique constraint "pk_item_lsh"'
    )
    assert a == b == 'ERROR: duplicate key value violates unique constraint "pk_item_lsh"'
    assert signature(
        "Task collect.source[be71b0a2-b0e2-492f-9493-6738f9810b11] failed after 12.5s"
    ) == ("Task collect.source[<uuid>] failed after <n>s")


def test_host_lines_take_the_time_of_the_last_json_line() -> None:
    lines = [
        f'{{"ts": "{T0.isoformat()}", "level": "info", "service": "cli", "logger": "news_insight.cards.service", "msg": "card run", "ready": 5, "failed": 1, "soft": 0}}',
        "Traceback (most recent call last):",
        '  File "x.py", line 1, in <module>',
        "httpx.HTTPStatusError: Client error '400 Bad Request' for url 'http://127.0.0.1:1234/v1/chat'",
    ]
    events = list(parse_lines("host:cards", lines))
    assert events[-1].level == "error" and events[-1].ts == T0
    report = analyse(events, since=T0 - timedelta(hours=1), until=T0)
    assert report.card_runs == {"ready": 5, "failed": 1, "soft": 0, "runs": 1}


def test_report_groups_errors_and_route_latency() -> None:
    events = list(parse_lines("api", UVICORN_TRACE * 3))
    report = analyse(events, since=T0 - timedelta(hours=1), until=T0 + timedelta(hours=1))
    assert report.errors["api"] == 3 and report.groups[0].count == 3
    assert report.routes["/api/public/insights"]["5xx"] == 3
    assert report.routes["/api/public/insights"]["p95"] == 4650
    text = render(report)
    assert "| api | " in text and "/api/public/insights" in text


def test_events_before_the_window_are_left_out() -> None:
    events = list(parse_lines("api", UVICORN_TRACE))
    report = analyse(events, since=T0 + timedelta(minutes=5), until=T0 + timedelta(hours=1))
    assert report.errors == {} and report.routes == {}
