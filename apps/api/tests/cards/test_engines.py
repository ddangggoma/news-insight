import json
import subprocess
from typing import Any

import httpx
import pytest

from news_insight.cards.engines import (
    AgyEngine,
    EngineError,
    QuotaExhausted,
    QwenEngine,
    parse_usage,
)
from news_insight.cards.schemas import CardInput

INPUTS = [CardInput(id=7, title="Pixel 11", source="9to5Google", language="en", excerpt=None)]
USAGE = (
    "Gemini Models\tWeekly Limit Remaining\t42%\t2026-10-10T03:49:33Z\n"
    "Gemini Models\tFive Hour Limit Remaining\t7%\t2026-10-03T16:18:41Z\n"
    "Claude and GPT models\tWeekly Limit Remaining\t100%\t2026-10-10T13:26:25Z\n"
)


class FakeRunner:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.calls: list[dict[str, Any]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, self.stderr)


def agy(runner: FakeRunner) -> AgyEngine:
    return AgyEngine(executable="agy", model="gemini-flash", timeout_seconds=30, runner=runner)


def test_usage_parses_gemini_limits_only() -> None:
    quota = parse_usage(USAGE)

    assert (quota.weekly, quota.five_hour) == (42, 7)
    assert quota.usable(min_weekly=10, min_five_hour=2)
    assert not quota.usable(min_weekly=50, min_five_hour=2)
    assert not parse_usage("nothing").usable(min_weekly=0, min_five_hour=0)


def test_agy_generates_with_schema_without_slash_commands_and_secrets() -> None:
    envelope = {"status": "SUCCESS", "structured_output": json.dumps({"cards": []})}
    runner = FakeRunner(json.dumps(envelope))

    output = agy(runner).generate(INPUTS)

    call = runner.calls[0]
    args = call["args"]
    assert args[:2] == ["agy", "-p"]
    assert '"Pixel 11"' in args[2]
    assert "--disable-slash-commands" in args
    assert args[args.index("--model") + 1] == "gemini-flash"
    assert "SOURCE_SECRET_GITHUB_TOKEN" not in call["env"]
    assert output.raw == {"cards": []}


@pytest.mark.parametrize(
    ("runner", "error"),
    [
        (
            FakeRunner(json.dumps({"status": "ERROR", "error": "RESOURCE_EXHAUSTED quota"})),
            QuotaExhausted,
        ),
        (FakeRunner("", returncode=1, stderr="429 rate limit"), QuotaExhausted),
        (FakeRunner(json.dumps({"status": "ERROR", "error": "boom"})), EngineError),
        (FakeRunner("not json"), EngineError),
        (FakeRunner(json.dumps({"status": "SUCCESS"})), EngineError),
    ],
)
def test_agy_failures(runner: FakeRunner, error: type[Exception]) -> None:
    with pytest.raises(error):
        agy(runner).generate(INPUTS)


def test_qwen_posts_schema_with_reasoning_off() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        content = json.dumps(
            {"cards": [{"id": 7, "title_ko": "픽셀 11", "summary_ko": [], "keywords": []}]}
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    engine = QwenEngine(
        base_url="http://lm:1234",
        model="qwen",
        timeout_seconds=5,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    output = engine.generate(INPUTS)

    assert seen[0]["reasoning_effort"] == "none"
    assert seen[0]["response_format"]["type"] == "json_schema"
    assert output.raw["cards"][0]["title_ko"] == "픽셀 11"


def test_qwen_errors_are_engine_errors() -> None:
    engine = QwenEngine(
        base_url="http://lm:1234",
        model="qwen",
        timeout_seconds=5,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )

    with pytest.raises(EngineError):
        engine.generate(INPUTS)
