import json
import logging

from fastapi.testclient import TestClient

from news_insight.main import create_app
from news_insight.observability import JsonFormatter
from news_insight.ops.checks import check_slow_requests


def test_json_formatter_includes_extra_fields() -> None:
    record = logging.LogRecord("x", logging.WARNING, __file__, 1, "collect failed", None, None)
    record.source_id = 7

    line = json.loads(JsonFormatter("worker").format(record))

    assert line["service"] == "worker" and line["level"] == "warning"
    assert line["msg"] == "collect failed" and line["source_id"] == 7


def test_api_responses_carry_a_request_id() -> None:
    client = TestClient(create_app())

    echoed = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    generated = client.get("/api/health")

    assert echoed.headers["x-request-id"] == "abc123"
    assert len(generated.headers["x-request-id"]) == 16


def test_slow_request_alert_needs_five_in_the_hour() -> None:
    entries = [f"{i}.0 /api/public/radar 7.10" for i in range(4)]

    assert check_slow_requests(entries) == []
    findings = check_slow_requests([*entries, "9.0 /api/public/items 5.20"])
    assert findings[0].key == "api_slow" and "/api/public/radar 4회" in findings[0].detail
