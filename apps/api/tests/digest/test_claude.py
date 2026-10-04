import json
import subprocess
from typing import Any

import pytest

from news_insight.digest.claude import ClaudeCli, ClaudeError, safe_env


class FakeRunner:
    def __init__(
        self, *, stdout: str = "", returncode: int = 0, raises: Exception | None = None
    ) -> None:
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.calls: list[dict[str, Any]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append({"args": args, **kwargs})
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "boom")


ENVELOPE = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "structured_output": {"headline": "h"},
    "total_cost_usd": 0.42,
    "modelUsage": {"claude-opus-x": {}},
}


def test_runs_tool_less_in_an_empty_directory_and_parses_output() -> None:
    runner = FakeRunner(stdout=json.dumps(ENVELOPE))
    client = ClaudeCli(executable="claude", timeout_seconds=30, runner=runner)

    result = client.generate({"tracks": []}, schema={"type": "object"}, model="opus")

    call = runner.calls[0]
    args = call["args"]
    assert args[:2] == ["claude", "-p"]
    assert args[args.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert args[args.index("--model") + 1] == "opus"
    assert json.loads(call["input"]) == {"tracks": []}
    assert call["timeout"] == 30 and call["cwd"]
    assert (result.structured, result.cost_usd, result.model) == (
        {"headline": "h"},
        0.42,
        "claude-opus-x",
    )


@pytest.mark.parametrize(
    ("runner", "message"),
    [
        (FakeRunner(returncode=1), "exited 1"),
        (FakeRunner(stdout="not json"), "non-JSON"),
        (FakeRunner(stdout=json.dumps({**ENVELOPE, "is_error": True})), "reported an error"),
        (
            FakeRunner(stdout=json.dumps({**ENVELOPE, "structured_output": None})),
            "no structured output",
        ),
        (FakeRunner(raises=subprocess.TimeoutExpired("claude", 30)), "timed out"),
        (FakeRunner(raises=FileNotFoundError("claude")), "cannot run"),
    ],
)
def test_failures_raise_claude_error(runner: FakeRunner, message: str) -> None:
    client = ClaudeCli(executable="claude", timeout_seconds=30, runner=runner)

    with pytest.raises(ClaudeError, match=message):
        client.generate({}, schema={}, model="opus")


def test_secrets_are_removed_from_the_child_environment() -> None:
    env = safe_env(
        {
            "PATH": "/bin",
            "HOME": "/Users/x",
            "SOURCE_SECRET_GITHUB_TOKEN": "t",
            "POSTGRES_PASSWORD": "p",
            "DATABASE_URL": "postgresql://",
            "CONSOLE_API_KEY": "k",
        }
    )

    assert env == {"PATH": "/bin", "HOME": "/Users/x"}
