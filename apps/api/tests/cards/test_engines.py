import json
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from news_insight.cards.engines import (
    AgyEngine,
    CodexEngine,
    EngineError,
    QuotaExhausted,
    QwenEngine,
    codex_quota,
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


ROLLOUT_LINE = json.dumps(
    {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "limit_id": "codex",
                "primary": {"used_percent": 24.0, "window_minutes": 10080},
                "secondary": None,
            },
        },
    }
)


class CodexRunner(FakeRunner):
    """Writes the session file Codex would leave behind for the thread it reports."""

    def __init__(self, stdout: str, sessions: Any, thread: str = "t-1", **kwargs: Any) -> None:
        super().__init__(stdout, **kwargs)
        self.sessions, self.thread = sessions, thread

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        day = self.sessions / "2026" / "10" / "05"
        day.mkdir(parents=True, exist_ok=True)
        (day / f"rollout-2026-10-05T20-00-00-{self.thread}.jsonl").write_text(
            f'{{"type":"session_meta"}}\n{ROLLOUT_LINE}\n', encoding="utf-8"
        )
        return super().__call__(args, **kwargs)


def codex_stdout(message: str | None, *, error: str | None = None) -> str:
    events: list[dict[str, Any]] = [{"type": "thread.started", "thread_id": "t-1"}]
    events.append({"type": "item.completed", "item": {"type": "error", "message": "code mode off"}})
    if message is not None:
        events.append(
            {"type": "item.completed", "item": {"type": "agent_message", "text": message}}
        )
    if error is not None:
        events.append({"type": "turn.failed", "error": {"message": error}})
    return "\n".join(json.dumps(e) for e in events)


def test_codex_runs_tool_less_reads_its_quota_and_removes_the_session(tmp_path: Any) -> None:
    runner = CodexRunner(codex_stdout(json.dumps({"cards": []})), tmp_path)
    engine = CodexEngine(
        executable="codex", model=None, timeout_seconds=30, sessions_dir=tmp_path, runner=runner
    )

    output = engine.generate(INPUTS)

    call = runner.calls[0]
    args = call["args"]
    assert args[:2] == ["codex", "exec"] and args[-1] == "-"
    assert '"Pixel 11"' in call["input"] and not any("Pixel 11" in a for a in args)
    for feature in ("shell_tool", "unified_exec", "browser_use", "computer_use", "plugins"):
        assert args[args.index(feature) - 1] == "--disable"
    assert "--ignore-user-config" in args and 'web_search="disabled"' in args
    assert "SOURCE_SECRET_GITHUB_TOKEN" not in call["env"]
    assert output.raw == {"cards": []}
    quota = engine.usage()  # from the session of the call above: no extra call
    assert (quota.weekly, quota.five_hour) == (76, 100) and len(runner.calls) == 1
    assert list(tmp_path.glob("**/rollout-*.jsonl")) == []


def test_codex_schema_is_strict_for_structured_outputs(tmp_path: Any) -> None:
    seen: dict[str, Any] = {}

    class Capture(CodexRunner):
        def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            path = Path(args[args.index("--output-schema") + 1])
            seen.update(json.loads(path.read_text(encoding="utf-8")))
            return super().__call__(args, **kwargs)

    runner = Capture(codex_stdout(json.dumps({"cards": []})), tmp_path)
    CodexEngine(
        executable="codex", model="m", timeout_seconds=30, sessions_dir=tmp_path, runner=runner
    ).generate(INPUTS)

    assert seen["additionalProperties"] is False
    item = seen["properties"]["cards"]["items"]
    assert item["additionalProperties"] is False and "companies" in item["required"]


def test_codex_usage_limit_is_a_quota_error(tmp_path: Any) -> None:
    runner = CodexRunner(
        codex_stdout(None, error="You've hit your usage limit. Try again later."), tmp_path
    )
    engine = CodexEngine(
        executable="codex", model=None, timeout_seconds=30, sessions_dir=tmp_path, runner=runner
    )
    with pytest.raises(QuotaExhausted):
        engine.generate(INPUTS)


def test_codex_quota_reads_the_last_snapshot() -> None:
    later = ROLLOUT_LINE.replace("24.0", "93.5")
    quota = codex_quota(f"{ROLLOUT_LINE}\nnot json\n{later}\n")
    assert quota is not None and quota.weekly == 6
    assert not quota.usable(min_weekly=10, min_five_hour=2)
    assert codex_quota('{"type":"session_meta"}') is None
