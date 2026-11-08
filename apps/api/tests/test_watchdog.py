"""The host watchdog (ops/watchdog/watchdog.py): checks from outside Docker, alert state, pushes."""

import ast
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

WATCHDOG_PATH = Path(__file__).resolve().parents[3] / "ops" / "watchdog" / "watchdog.py"


def load_watchdog() -> ModuleType:
    spec = importlib.util.spec_from_file_location("host_watchdog", WATCHDOG_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["host_watchdog"] = module
    spec.loader.exec_module(module)
    return module


wd = load_watchdog()
# 10:00 KST: after the briefing deadline
NOW = datetime(2026, 11, 4, 1, 0, tzinfo=UTC)
HEALTHY_PS = "\n".join(
    f"{service}\trunning\tUp 9 hours{' (healthy)' if service in ('api', 'web') else ''}"
    for service in wd.SERVICES
)


def iso(moment: datetime) -> str:
    return moment.isoformat()


def facts(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "last_success": iso(NOW - timedelta(minutes=1)),
        "last_card_run": iso(NOW - timedelta(minutes=12)),
        "card_notes": ["agy quota reserved: switching to claude", ""],
        "briefings": [{"version": 1, "status": "published", "gates": []}],
        "alerts": [],
    }
    base.update(overrides)
    return base


class FakeRunner:
    """Answers by command: `docker info`, `docker ps`, `docker exec … psql`, `pgrep`, `open`,
    `osascript`. `docker_fails` failing `docker info` calls come before it answers (docker=False:
    it never answers); `app` says whether Docker Desktop's process exists."""

    def __init__(
        self,
        *,
        docker: bool = True,
        docker_fails: int = 0,
        app: bool = True,
        ps: str = HEALTHY_PS,
        db: dict[str, Any] | None = None,
        db_error: str = "",
        osascript: int = 0,
    ) -> None:
        self.docker, self.ps, self.db, self.db_error = docker, ps, db, db_error
        self.docker_fails, self.app = docker_fails, app
        self.osascript = osascript
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], timeout: float) -> tuple[int, str]:
        self.calls.append(args)
        if args[:2] == ["docker", "info"]:
            if not self.docker or self.docker_fails > 0:
                self.docker_fails -= 1
                return 124, "Command timed out after 20 seconds"
            return 0, "29.8.1\n"
        if args[0] == "pgrep":
            return (0, "56944\n") if self.app else (1, "")
        if args[:2] == ["docker", "ps"]:
            return 0, self.ps
        if args[:2] == ["docker", "exec"]:
            if self.db_error:
                return 2, self.db_error
            # json_agg puts line breaks between array elements
            return 0, json.dumps(self.db if self.db is not None else facts(), indent=1) + "\n"
        if args[0] == "osascript":
            return self.osascript, ""
        return 0, ""


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, bool]] = []

    def send(self, title: str, message: str, *, urgent: bool) -> list[str]:
        self.sent.append((title, message, urgent))
        return ["test"]


def keys(findings: Any) -> list[str]:
    return sorted(problem.key for problem in findings.problems)


def test_runs_on_the_system_python_with_the_standard_library_only() -> None:
    tree = ast.parse(WATCHDOG_PATH.read_text(encoding="utf-8"), feature_version=(3, 9))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-11-04T01:02:15.23+00:00", datetime(2026, 11, 4, 1, 2, 15, 230000, tzinfo=UTC)),
        ("2026-11-04T10:02:15+09:00", datetime(2026, 11, 4, 1, 2, 15, tzinfo=UTC)),
        ("2026-11-04T01:02:15.1234567Z", datetime(2026, 11, 4, 1, 2, 15, 123456, tzinfo=UTC)),
        ("", None),
        ("not a time", None),
    ],
)
def test_reads_postgres_times_python_39_would_refuse(text: str, expected: datetime | None) -> None:
    assert wd._when(text) == expected


def test_reads_the_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nPOSTGRES_USER=news\nexport WATCHDOG_NTFY_TOPIC='abc def'\n\nBROKEN\nX=\"q\"\n",
        encoding="utf-8",
    )
    assert wd.read_env(env) == {"POSTGRES_USER": "news", "WATCHDOG_NTFY_TOPIC": "abc def", "X": "q"}
    assert wd.read_env(tmp_path / "missing") == {}


def test_a_healthy_stack_has_no_problems() -> None:
    findings = wd.inspect({}, NOW, run=FakeRunner(), status=lambda url: 200)
    assert findings.problems == []
    assert not findings.docker_down and findings.db_read


def no_pause(seconds: float) -> None:
    pass


def test_docker_off_stops_the_other_checks_and_asks_to_start_it() -> None:
    runner = FakeRunner(docker=False, app=False)
    pauses: list[float] = []
    findings = wd.inspect({}, NOW, run=runner, status=lambda url: 0, pause=pauses.append)
    assert keys(findings) == ["docker_down"]
    assert findings.docker_down and not findings.docker_app
    assert findings.problems[0].title == "Docker가 꺼져 있습니다"
    assert [call[:2] for call in runner.calls] == [["docker", "info"]] * 3 + [["pgrep", "-x"]]
    assert pauses == [wd.DOCKER_RETRY_PAUSE] * 2


def test_a_stuck_engine_with_the_app_running_is_reported_not_restarted() -> None:
    findings = wd.inspect({}, NOW, run=FakeRunner(docker=False), status=lambda u: 0, pause=no_pause)
    assert findings.docker_down and findings.docker_app
    (problem,) = findings.problems
    assert problem.title == "Docker가 응답하지 않습니다"
    assert "exit 124: Command timed out after 20 seconds" in problem.detail


def test_docker_info_answering_on_a_retry_is_no_problem() -> None:
    runner = FakeRunner(docker_fails=2)
    findings = wd.inspect({}, NOW, run=runner, status=lambda url: 200, pause=no_pause)
    assert findings.problems == [] and not findings.docker_down
    assert sum(call[:2] == ["docker", "info"] for call in runner.calls) == 3
    assert not any(call[0] == "pgrep" for call in runner.calls)


def test_docker_down_alerts_only_on_the_second_run_in_a_row() -> None:
    state: dict[str, Any] = {}
    notifier = RecordingNotifier()
    down = wd.Findings([problem("docker_down")], docker_down=True, docker_app=True)
    assert wd.step(state, down, NOW, notifier) == []
    assert wd.step(state, wd.Findings([]), NOW + timedelta(minutes=5), notifier) == []
    assert wd.step(state, down, NOW + timedelta(minutes=10), notifier) == []
    assert wd.step(state, down, NOW + timedelta(minutes=15), notifier) == [
        "[Daily IT] 긴급: title docker_down"
    ]


def test_stopped_missing_and_unhealthy_containers() -> None:
    ps = "\n".join(
        [
            "postgres\texited\tExited (0) 3 hours ago",
            "redis\trunning\tUp 4 days (healthy)",
            "api\trunning\tUp 1 minute (unhealthy)",
            "worker\tcreated\tCreated",
            "worker\trunning\tUp 9 hours (healthy)",  # a half-made twin next to the real one
            "web\trunning\tUp 9 hours (healthy)",
            "caddy\trunning\tUp 4 days",
        ]
    )
    problem = wd.check_containers(FakeRunner(ps=ps))
    assert problem is not None
    assert problem.title == "컨테이너 3개가 멈춰 있습니다"
    assert problem.detail.startswith("postgres(exited), api(unhealthy), scheduler(missing)")


def test_site_down_through_the_edge_proxy() -> None:
    seen: list[str] = []

    def status(url: str) -> int:
        seen.append(url)
        return 502

    findings = wd.inspect({"CADDY_HTTPS_PORT": "8700"}, NOW, run=FakeRunner(), status=status)
    assert keys(findings) == ["site_down"]
    assert seen == ["https://127.0.0.1:8700/api/health"]


def test_database_unreachable_leaves_its_checks_unknown() -> None:
    findings = wd.inspect(
        {}, NOW, run=FakeRunner(db_error="No such container"), status=lambda u: 200
    )
    assert keys(findings) == ["db_unreachable"]
    assert not findings.db_read
    assert not findings.checked("collection_stale")
    assert not findings.checked("ops:freeze_missing")
    assert findings.checked("site_down")


def test_collection_and_cards_stale() -> None:
    db = facts(
        last_success=iso(NOW - timedelta(hours=2, minutes=5)),
        last_card_run=iso(NOW - timedelta(minutes=50)),
    )
    problems = {p.key: p for p in wd.check_db(db, NOW)}
    assert set(problems) == {"collection_stale", "cards_stale"}
    assert "2시간 5분 동안" in problems["collection_stale"].detail
    assert problems["cards_stale"].severity == "warning"
    assert {p.key for p in wd.check_db(facts(last_success=None), NOW)} == {"collection_stale"}


def test_claude_login_needs_two_failed_card_runs() -> None:
    lapsed = "switching to claude; claude exited 1: Not logged in · Please run /login"
    expired = "claude exited 1: Failed to authenticate: OAuth session expired"
    assert [p.key for p in wd.check_db(facts(card_notes=[lapsed, expired]), NOW)] == [
        "claude_login"
    ]
    assert wd.check_db(facts(card_notes=[lapsed, "switching to claude"]), NOW) == []


def test_briefing_due_after_0530_kst_with_the_failed_gates() -> None:
    blocked = [
        {
            "version": 3,
            "status": "blocked",
            "gates": [
                {"name": "official", "label": "1차 공식 출처 비중", "passed": False},
                {"name": "region_jp", "label": "jp 비중(권고)", "passed": False, "blocking": False},
                {"name": "korean", "label": "한국 출처 비중", "passed": True},
            ],
        }
    ]
    early = datetime(2026, 11, 3, 20, 25, tzinfo=UTC)  # 05:25 KST
    assert wd.check_briefing(blocked, early) == []
    (problem,) = wd.check_briefing(blocked, NOW)
    assert problem.key == "briefing_missing:2026-11-04"
    assert "v3 차단, 실패 게이트: 1차 공식 출처 비중." in problem.detail
    (missing,) = wd.check_briefing([], NOW)
    assert "하나도 없습니다" in missing.detail
    published = [*blocked, {"version": 4, "status": "published", "gates": []}]
    assert wd.check_briefing(published, NOW) == []


def test_forwards_other_critical_ops_alerts_only() -> None:
    alerts = [
        {"key": "freeze_missing", "severity": "critical", "title": "동결 없음", "detail": "d"},
        {"key": "publish_sla", "severity": "critical", "title": "브리핑 없음", "detail": "d"},
        {"key": "host_memory", "severity": "warning", "title": "메모리", "detail": "d"},
    ]
    problems = wd.check_db(facts(alerts=alerts), NOW)
    assert [(p.key, p.title) for p in problems] == [("ops:freeze_missing", "동결 없음")]
    assert wd.CONSOLE_HINT in problems[0].detail


def problem(key: str, severity: str = "critical") -> Any:
    return wd.Problem(key, severity, f"title {key}", f"detail {key}")


def test_alerts_once_repeats_critical_every_six_hours_and_reports_recovery() -> None:
    state: dict[str, Any] = {}
    notifier = RecordingNotifier()
    down = wd.Findings([problem("collection_stale")])
    assert wd.step(state, down, NOW, notifier) == ["[Daily IT] 긴급: title collection_stale"]
    assert wd.step(state, down, NOW + timedelta(minutes=5), notifier) == []
    later = NOW + timedelta(hours=6, minutes=1)
    assert wd.step(state, down, later, notifier) == [
        "[Daily IT] 긴급 계속(6시간 1분): title collection_stale"
    ]
    recovered = wd.step(state, wd.Findings([]), later + timedelta(minutes=5), notifier)
    assert recovered == ["[Daily IT] 복구: title collection_stale"]
    assert notifier.sent[-1] == (recovered[0], "6시간 6분 만에 정상으로 돌아왔습니다", False)
    assert state["problems"] == {}


def test_warnings_do_not_repeat_and_confirmation_waits_for_a_second_run() -> None:
    state: dict[str, Any] = {}
    notifier = RecordingNotifier()
    findings = wd.Findings([problem("containers_down"), problem("cards_stale", "warning")])
    assert wd.step(state, findings, NOW, notifier) == ["[Daily IT] 주의: title cards_stale"]
    assert wd.step(state, findings, NOW + timedelta(minutes=5), notifier) == [
        "[Daily IT] 긴급: title containers_down"
    ]
    assert wd.step(state, findings, NOW + timedelta(hours=7), notifier) == [
        "[Daily IT] 긴급 계속(7시간 0분): title containers_down"
    ]
    assert [urgent for _, _, urgent in notifier.sent] == [False, True, True]


def test_a_problem_gone_before_it_was_confirmed_clears_silently() -> None:
    state: dict[str, Any] = {}
    notifier = RecordingNotifier()
    wd.step(state, wd.Findings([problem("site_down")]), NOW, notifier)
    assert wd.step(state, wd.Findings([]), NOW + timedelta(minutes=5), notifier) == []
    assert notifier.sent == [] and state["problems"] == {}


def test_unchecked_problems_stay_open_while_docker_is_down() -> None:
    state: dict[str, Any] = {}
    notifier = RecordingNotifier()
    wd.step(state, wd.Findings([problem("collection_stale")]), NOW, notifier)
    docker_down = wd.Findings([problem("docker_down")], docker_down=True)
    assert wd.step(state, docker_down, NOW + timedelta(minutes=4), notifier) == []
    sent = wd.step(state, docker_down, NOW + timedelta(minutes=5), notifier)
    assert sent == ["[Daily IT] 긴급: title docker_down"]
    assert set(state["problems"]) == {"collection_stale", "docker_down"}
    db_down = wd.Findings([problem("db_unreachable")], db_read=False)
    sent = wd.step(state, db_down, NOW + timedelta(minutes=10), notifier)
    assert sent == ["[Daily IT] 복구: title docker_down"]
    assert set(state["problems"]) == {"collection_stale", "db_unreachable"}


def test_a_missing_briefing_does_not_repeat_and_expires_with_the_day() -> None:
    state: dict[str, Any] = {}
    notifier = RecordingNotifier()
    missing = wd.Findings([problem("briefing_missing:2026-11-04")])
    assert len(wd.step(state, missing, NOW, notifier)) == 1
    assert wd.step(state, missing, NOW + timedelta(hours=13), notifier) == []
    next_morning = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)  # 01:00 KST on 11-05
    assert wd.step(state, wd.Findings([]), next_morning, notifier) == []
    assert state["problems"] == {}


def test_a_briefing_published_late_the_same_day_is_reported() -> None:
    state: dict[str, Any] = {}
    notifier = RecordingNotifier()
    wd.step(state, wd.Findings([problem("briefing_missing:2026-11-04")]), NOW, notifier)
    sent = wd.step(state, wd.Findings([]), NOW + timedelta(hours=1), notifier)
    assert sent == ["[Daily IT] 복구: title briefing_missing:2026-11-04"]


def test_starts_docker_desktop_at_most_every_ten_minutes() -> None:
    runner = FakeRunner()
    state: dict[str, Any] = {}
    assert wd.open_docker(state, NOW, runner)
    assert not wd.open_docker(state, NOW + timedelta(minutes=5), runner)
    assert wd.open_docker(state, NOW + timedelta(minutes=11), runner)
    assert runner.calls == [["open", "-a", "Docker"], ["open", "-a", "Docker"]]


def test_state_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "watchdog-state.json"
    assert wd.load_state(path) == {}
    wd.save_state(path, {"problems": {"docker_down": {"title": "Docker가 꺼져 있습니다"}}})
    assert wd.load_state(path)["problems"]["docker_down"]["title"] == "Docker가 꺼져 있습니다"
    path.write_text("[]", encoding="utf-8")
    assert wd.load_state(path) == {}


def test_channels_follow_the_env() -> None:
    assert wd.Notifier({}).channels() == ["mac"]
    env = {
        "WATCHDOG_MAC_NOTIFY": "false",
        "WATCHDOG_NTFY_TOPIC": "t",
        "WATCHDOG_TELEGRAM_BOT_TOKEN": "x",
    }
    assert wd.Notifier(env).channels() == ["ntfy"]
    env["WATCHDOG_TELEGRAM_CHAT_ID"] = "1"
    assert wd.Notifier(env).channels() == ["ntfy", "telegram"]


def test_pushes_utf8_json_to_ntfy_and_telegram_and_survives_a_failed_channel() -> None:
    posted: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def post(url: str, body: bytes, headers: dict[str, str]) -> int:
        posted.append((url, json.loads(body.decode("utf-8")), headers))
        return 500 if "telegram" in url else 200

    runner = FakeRunner(osascript=1)
    env = {
        "WATCHDOG_NTFY_TOPIC": "news-insight-x7",
        "WATCHDOG_NTFY_TOKEN": "tk",
        "WATCHDOG_TELEGRAM_BOT_TOKEN": "123:abc",
        "WATCHDOG_TELEGRAM_CHAT_ID": "42",
    }
    delivered = wd.Notifier(env, run=runner, post=post).send("제목", "본문", urgent=True)
    assert delivered == ["ntfy"]
    (ntfy_url, ntfy, ntfy_headers), (telegram_url, telegram, _) = posted
    assert ntfy_url == "https://ntfy.sh"
    assert ntfy == {
        "topic": "news-insight-x7",
        "title": "제목",
        "message": "본문",
        "priority": 5,
        "tags": ["rotating_light"],
    }
    assert ntfy_headers["Authorization"] == "Bearer tk"
    assert telegram_url == "https://api.telegram.org/bot123:abc/sendMessage"
    assert telegram == {"chat_id": "42", "text": "제목\n본문", "disable_notification": False}


def test_mac_notification_passes_the_text_as_arguments() -> None:
    runner = FakeRunner()
    title, message = 'say "hi"', 'end tell" & do shell script "rm -rf /'
    assert wd.Notifier({}, run=runner).send(title, message, urgent=False) == ["mac"]
    (call,) = runner.calls
    assert call[0] == "osascript" and call[-2:] == [title, message]
    script = " ".join(call[1:-2])
    assert message not in script and title not in script
