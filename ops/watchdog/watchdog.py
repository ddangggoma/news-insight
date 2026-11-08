#!/usr/bin/env python3
"""Host watchdog: notices from outside Docker when the stack, collection, cards or the briefing
stop, and pushes the alert to a phone.

The ops check (`ops.check`) runs in Celery, inside the stack it watches, and its alerts show on
the console only. On 2026-10-30 the Mac rebooted, Docker Desktop did not start again, and the
site, collection and cards stood still for 21 hours with no alert at all; the 10-31 briefing
never went out. This job runs from launchd every 5 minutes on the system python3 (standard
library only, Python 3.9), so it works while Docker, Postgres or the app venv are down:

  - Docker not answering (3 tries in a run, 2 runs in a row): alert, and start Docker Desktop
    (`open -a Docker`) when its app is not running at all
  - app containers stopped or unhealthy, the site not answering through the edge proxy
  - no successful collection for 45 minutes, no card run for 45 minutes
  - the host Claude CLI logged out (two card runs in a row say so; the 05:00 digest needs it)
  - after 05:30 KST, no published briefing today (the blocking gates in the message)
  - any other critical alert the ops check has open (forwarded)

An alert goes out once when a problem is confirmed, again every 6 hours while a critical one
lasts, and once more when it clears. Channels (all optional, set in .env): a macOS notification,
ntfy (WATCHDOG_NTFY_TOPIC) and Telegram (WATCHDOG_TELEGRAM_BOT_TOKEN, _CHAT_ID).

    /usr/bin/python3 ops/watchdog/watchdog.py --root /Users/ggoma/WorkSpace/NEWS_INSIGHT-live
    /usr/bin/python3 ops/watchdog/watchdog.py --dry-run       # print what it finds, send nothing
    /usr/bin/python3 ops/watchdog/watchdog.py --test-notify   # one test message on every channel

scripts/install-watchdog.sh registers it; docs/runbooks/operations.md §14 explains it.
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
UTC = timezone.utc  # noqa: UP017 - datetime.UTC needs Python 3.11; launchd runs 3.9
PROJECT = "news-insight"
SERVICES = ("postgres", "redis", "api", "worker", "scheduler", "web", "caddy")
COLLECTION_STALE = timedelta(minutes=45)
CARDS_STALE = timedelta(minutes=45)
BRIEFING_DUE = (5, 30)  # KST hour, minute: the 05:00 run and its first retry have had time
REPEAT_CRITICAL = timedelta(hours=6)
DOCKER_REOPEN = timedelta(minutes=10)
HEARTBEAT = timedelta(hours=1)
# runs in a row a problem must be seen before it is sent: a container restarting during a
# deploy (about a minute) or one transient "Not logged in" (2026-11-04 05:49) is not an outage
CONFIRM = {
    "docker_down": 2,
    "containers_down": 2,
    "site_down": 2,
    "db_unreachable": 2,
    "claude_login": 2,
}
# `docker info` from launchd sometimes failed while the stack kept running: 19 "Docker is off"
# alerts on 11-07..08, containers up for 3 days, collection never paused, with swap near full.
# A run calls Docker down only after every attempt fails, and alerts after two such runs.
DOCKER_ATTEMPTS = 3
DOCKER_TIMEOUT = 20.0
DOCKER_RETRY_PAUSE = 10.0
DOCKER_APP = "com.docker.backend"  # the Docker Desktop process; absent until the app starts
# the briefing retries end at 10:00: repeating "not published" all day would only be noise
NO_REPEAT = frozenset({"briefing_missing"})
# keys read from the database: while it (or Docker) is unreachable they are unknown, not cleared
DB_KEYS = ("collection_stale", "cards_stale", "claude_login", "briefing_missing", "ops:")
# the ops check's own alerts that this job already reports in its own words
COVERED = frozenset({"publish_sla", "publish_blocked", "collection_stalled", "cards_stalled"})
LOGIN_FAILED = re.compile(r"Not logged in|Failed to authenticate|OAuth session expired|/login")
CONSOLE_HINT = "콘솔 → 운영 알림"

Runner = Callable[[list[str], float], tuple[int, str]]
Poster = Callable[[str, bytes, dict[str, str]], int]


@dataclass(frozen=True)
class Problem:
    key: str
    severity: str  # "critical" or "warning"
    title: str
    detail: str


# ---------------------------------------------------------------- I/O the tests replace


def run_command(args: list[str], timeout: float) -> tuple[int, str]:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, str(error)
    return done.returncode, (done.stdout or "") + (done.stderr if done.returncode else "")


def http_status(url: str, timeout: float = 20.0) -> int:
    """Status code of a GET; 0 when nothing answers. Caddy's local certificate is not in the
    system trust store, so loopback checks skip verification."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=context) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except (urllib.error.URLError, OSError, ValueError):
        return 0


def http_post(url: str, body: bytes, headers: dict[str, str]) -> int:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except (urllib.error.URLError, OSError, ValueError):
        return 0


# ---------------------------------------------------------------- configuration


def read_env(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of the repo .env (the same file compose reads); quotes stripped."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        values[key] = value.strip().strip("\"'")
    return values


# ---------------------------------------------------------------- checks


def check_docker(run: Runner, pause: Callable[[float], None] = time.sleep) -> tuple[bool, str]:
    """Whether the Docker engine answers, tried DOCKER_ATTEMPTS times; the last failure's text."""
    reason = ""
    for attempt in range(DOCKER_ATTEMPTS):
        if attempt:
            pause(DOCKER_RETRY_PAUSE)
        code, out = run(["docker", "info", "--format", "{{.ServerVersion}}"], DOCKER_TIMEOUT)
        if code == 0:
            if attempt:
                log(f"docker info answered on attempt {attempt + 1} after: {reason}")
            return True, ""
        reason = f"exit {code}: {' '.join(out.split())[:200] or 'no output'}"
    return False, reason


def docker_app_running(run: Runner) -> bool:
    """Docker Desktop's backend process exists (the engine may still be starting or stuck)."""
    code, _ = run(["pgrep", "-x", DOCKER_APP], 10)
    return code == 0


def check_containers(run: Runner) -> Problem | None:
    code, out = run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
            "--format",
            '{{.Label "com.docker.compose.service"}}\t{{.State}}\t{{.Status}}',
        ],
        30,
    )
    if code != 0:
        return Problem("containers_down", "critical", "컨테이너 상태를 읽지 못했습니다", out[:200])
    states: dict[str, tuple[str, str]] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        # a half-made container from a stuck deploy can sit next to the real one
        if (
            len(parts) == 3
            and parts[0] in SERVICES
            and (parts[0] not in states or parts[1] == "running")
        ):
            states[parts[0]] = (parts[1], parts[2])
    bad = []
    for service in SERVICES:
        state, status = states.get(service, ("missing", ""))
        if state != "running":
            bad.append(f"{service}({state})")
        elif "unhealthy" in status:
            bad.append(f"{service}(unhealthy)")
    if not bad:
        return None
    return Problem(
        "containers_down",
        "critical",
        f"컨테이너 {len(bad)}개가 멈춰 있습니다",
        ", ".join(bad) + ". 운영 트리에서 `docker compose ps` 확인 후 "
        "`docker compose up -d --no-build <서비스>` (operations.md §11)",
    )


def check_site(port: str, status: Callable[[str], int]) -> Problem | None:
    url = f"https://127.0.0.1:{port}/api/health"
    code = status(url)
    if code == 200:
        return None
    seen = f"HTTP {code}" if code else "응답 없음"
    return Problem(
        "site_down",
        "critical",
        "사이트가 응답하지 않습니다",
        f"{url}: {seen}. ops/logs/edge.log(엣지 프록시)와 caddy·api 컨테이너 확인",
    )


DB_QUERY = """
select json_build_object(
  'last_success', (select max(last_success_at) from source_runtimes),
  'last_card_run', (select max(started_at) from card_runs),
  'card_notes', (select coalesce(json_agg(coalesce(note, '')), '[]'::json)
                 from (select note from card_runs order by id desc limit 2) recent),
  'briefings', (select coalesce(json_agg(json_build_object(
                   'version', version, 'status', status, 'gates', gates)
                 order by version), '[]'::json)
                from briefings where briefing_date = (now() at time zone 'Asia/Seoul')::date),
  'alerts', (select coalesce(json_agg(json_build_object(
                'key', key, 'severity', severity, 'title', title, 'detail', detail)), '[]'::json)
             from ops_alerts where resolved_at is null)
)
"""


def read_db(run: Runner, env: dict[str, str]) -> tuple[dict[str, Any] | None, str]:
    user = env.get("POSTGRES_USER") or "news"
    database = env.get("POSTGRES_DB") or "news_insight"
    code, out = run(
        [
            "docker",
            "exec",
            f"{PROJECT}-postgres-1",
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            DB_QUERY,
        ],
        60,
    )
    if code != 0:
        return None, out.strip()[:200]
    try:
        # json_agg puts line breaks between elements, so the value spans lines
        facts = json.loads(out.strip())
    except ValueError:
        return None, out.strip()[:200]
    return (facts, "") if isinstance(facts, dict) else (None, out.strip()[:200])


FRACTION = re.compile(r"\.(\d+)")


def _when(value: str | None) -> datetime | None:
    """ISO time from Postgres JSON or this job's state. Postgres drops trailing zeros of the
    fraction (".12+00:00"), which Python 3.9's fromisoformat refuses: pad it to 6 digits."""
    if not value:
        return None
    text = FRACTION.sub(lambda m: "." + m[1][:6].ljust(6, "0"), str(value), count=1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def _age(minutes: timedelta) -> str:
    total = int(minutes.total_seconds() // 60)
    return f"{total // 60}시간 {total % 60}분" if total >= 60 else f"{total}분"


def check_db(facts: dict[str, Any], now: datetime) -> list[Problem]:
    problems: list[Problem] = []
    last_success = _when(facts.get("last_success"))
    if last_success is None or now - last_success > COLLECTION_STALE:
        since = f"{_age(now - last_success)} 동안" if last_success else "기록이"
        problems.append(
            Problem(
                "collection_stale",
                "critical",
                "수집이 멈췄습니다",
                f"성공한 수집이 {since} 없습니다. worker·scheduler·redis 컨테이너 확인",
            )
        )
    last_card = _when(facts.get("last_card_run"))
    if last_card is None or now - last_card > CARDS_STALE:
        since = _age(now - last_card) if last_card else "기록 없음"
        problems.append(
            Problem(
                "cards_stale",
                "warning",
                "카드 생성이 멈췄습니다",
                f"마지막 카드 실행 {since} 전. "
                "`launchctl print gui/$(id -u)/com.newsinsight.cards`와 ops/logs/cards.log 확인",
            )
        )
    notes = [str(note) for note in facts.get("card_notes") or []]
    if notes and all(LOGIN_FAILED.search(note) for note in notes):
        problems.append(
            Problem(
                "claude_login",
                "critical",
                "Claude CLI 로그인이 풀렸습니다",
                "카드(Claude 레인)와 05:00 다이제스트가 실패합니다. 이 Mac의 터미널에서 "
                "`claude`를 실행해 /login 하세요",
            )
        )
    problems.extend(check_briefing(facts.get("briefings") or [], now))
    for alert in facts.get("alerts") or []:
        if alert.get("severity") != "critical" or alert.get("key") in COVERED:
            continue
        problems.append(
            Problem(
                f"ops:{alert.get('key')}",
                "critical",
                str(alert.get("title") or alert.get("key")),
                f"{alert.get('detail') or ''} ({CONSOLE_HINT})".strip(),
            )
        )
    return problems


def check_briefing(briefings: list[dict[str, Any]], now: datetime) -> list[Problem]:
    local = now.astimezone(KST)
    if (local.hour, local.minute) < BRIEFING_DUE:
        return []
    if any(b.get("status") == "published" for b in briefings):
        return []
    if not briefings:
        detail = (
            "오늘 브리핑 버전이 하나도 없습니다(발행 작업이 안 돌았거나 실패). "
            "ops/logs/digest.log 확인"
        )
    else:
        latest = briefings[-1]
        failed = [
            str(g.get("label") or g.get("name"))
            for g in latest.get("gates") or []
            if g.get("blocking", True) and not g.get("passed", True)
        ]
        detail = (
            f"v{latest.get('version')} 차단, 실패 게이트: {', '.join(failed) or '알 수 없음'}. "
            "Fail-safe로 전일본이 보입니다. 06·07·08·10시에 다시 시도합니다"
        )
    key = f"briefing_missing:{local.date().isoformat()}"
    return [Problem(key, "critical", "오늘 브리핑이 발행되지 않았습니다", detail)]


@dataclass
class Findings:
    problems: list[Problem]
    docker_down: bool = False
    docker_app: bool = True  # False: Docker Desktop is not running at all; the caller starts it
    db_read: bool = True  # False: the database keys were not checked this run

    def checked(self, key: str) -> bool:
        if self.docker_down:
            return key == "docker_down"
        return self.db_read or not key.startswith(DB_KEYS)


def inspect(
    env: dict[str, str],
    now: datetime,
    run: Runner = run_command,
    status: Callable[[str], int] = http_status,
    pause: Callable[[float], None] = time.sleep,
) -> Findings:
    answered, reason = check_docker(run, pause)
    if not answered:
        app = docker_app_running(run)
        log(f"docker info failed {DOCKER_ATTEMPTS} times ({reason}); Docker Desktop running: {app}")
        if app:
            problem = Problem(
                "docker_down",
                "critical",
                "Docker가 응답하지 않습니다",
                "Docker Desktop은 실행 중인데 엔진이 응답하지 않습니다. 사이트·수집·카드가 멈췄을 "
                f"수 있습니다. 메모리(스왑)와 Docker Desktop 상태를 확인하세요. ({reason})",
            )
        else:
            problem = Problem(
                "docker_down",
                "critical",
                "Docker가 꺼져 있습니다",
                "사이트·수집·카드·발행이 모두 멈춘 상태입니다. Docker Desktop을 시작합니다. "
                "재부팅 뒤라면 Docker Desktop 설정의 "
                "'Start Docker Desktop when you sign in'을 켜 두세요",
            )
        return Findings([problem], docker_down=True, docker_app=app)
    problems: list[Problem] = []
    containers = check_containers(run)
    if containers:
        problems.append(containers)
    site = check_site(env.get("CADDY_HTTPS_PORT") or "8700", status)
    if site:
        problems.append(site)
    facts, error = read_db(run, env)
    db_read = facts is not None
    if facts is None:
        problems.append(
            Problem(
                "db_unreachable",
                "critical",
                "데이터베이스에 연결하지 못했습니다",
                f"postgres 컨테이너 확인. {error}".strip(),
            )
        )
    else:
        problems.extend(check_db(facts, now))
    return Findings(problems, db_read=db_read)


# ---------------------------------------------------------------- notifications


class Notifier:
    def __init__(self, env: dict[str, str], run: Runner = run_command, post: Poster = http_post):
        self.env, self.run, self.post = env, run, post

    def channels(self) -> list[str]:
        names = []
        if self.env.get("WATCHDOG_MAC_NOTIFY", "true").lower() not in ("0", "false", "no"):
            names.append("mac")
        if self.env.get("WATCHDOG_NTFY_TOPIC"):
            names.append("ntfy")
        if self.env.get("WATCHDOG_TELEGRAM_BOT_TOKEN") and self.env.get(
            "WATCHDOG_TELEGRAM_CHAT_ID"
        ):
            names.append("telegram")
        return names

    def send(self, title: str, message: str, *, urgent: bool) -> list[str]:
        """Every configured channel; the names that took the message."""
        delivered = []
        for name in self.channels():
            try:
                ok = getattr(self, f"_{name}")(title, message, urgent)
            except Exception as error:  # noqa: BLE001 - one channel must not stop the others
                log(f"notify {name} failed: {error}")
                ok = False
            if ok:
                delivered.append(name)
            else:
                log(f"notify {name} failed")
        return delivered

    def _mac(self, title: str, message: str, urgent: bool) -> bool:
        # the text goes in as arguments, never into the script source
        sound = ' sound name "Sosumi"' if urgent else ""
        code, _ = self.run(
            [
                "osascript",
                "-e",
                "on run argv",
                "-e",
                f"display notification (item 2 of argv) with title (item 1 of argv){sound}",
                "-e",
                "end run",
                title,
                message[:240],
            ],
            15,
        )
        return code == 0

    def _ntfy(self, title: str, message: str, urgent: bool) -> bool:
        server = (self.env.get("WATCHDOG_NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
        body = {
            "topic": self.env["WATCHDOG_NTFY_TOPIC"],
            "title": title,
            "message": message,
            "priority": 5 if urgent else 3,
            "tags": ["rotating_light" if urgent else "white_check_mark"],
        }
        headers = {"Content-Type": "application/json"}
        if self.env.get("WATCHDOG_NTFY_TOKEN"):
            headers["Authorization"] = f"Bearer {self.env['WATCHDOG_NTFY_TOKEN']}"
        code = self.post(server, json.dumps(body, ensure_ascii=False).encode("utf-8"), headers)
        return 200 <= code < 300

    def _telegram(self, title: str, message: str, urgent: bool) -> bool:
        token = self.env["WATCHDOG_TELEGRAM_BOT_TOKEN"]
        body = {
            "chat_id": self.env["WATCHDOG_TELEGRAM_CHAT_ID"],
            "text": f"{title}\n{message}",
            "disable_notification": not urgent,
        }
        code = self.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json.dumps(body, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
        return 200 <= code < 300


# ---------------------------------------------------------------- state and the run


def log(message: str) -> None:
    print(f"{datetime.now(KST).isoformat(timespec='seconds')} watchdog {message}", flush=True)


def load_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def label(severity: str) -> str:
    return "긴급" if severity == "critical" else "주의"


def step(
    state: dict[str, Any],
    findings: Findings,
    now: datetime,
    notifier: Notifier,
) -> list[str]:
    """Update the state with this run's problems and send what is due; the messages sent."""
    known: dict[str, Any] = state.setdefault("problems", {})
    sent: list[str] = []
    current = {problem.key: problem for problem in findings.problems}
    today = f"briefing_missing:{now.astimezone(KST).date().isoformat()}"
    for key, problem in current.items():
        entry = known.get(key) or {"first_seen": now.isoformat(), "count": 0, "notified_at": None}
        entry.update(count=entry["count"] + 1, severity=problem.severity, title=problem.title)
        known[key] = entry
        notified = _when(entry.get("notified_at"))
        if notified is None and entry["count"] >= CONFIRM.get(key, 1):
            title = f"[Daily IT] {label(problem.severity)}: {problem.title}"
        elif (
            notified is not None
            and problem.severity == "critical"
            and not key.startswith(tuple(NO_REPEAT))
            and now - notified >= REPEAT_CRITICAL
        ):
            since = _age(now - (_when(entry["first_seen"]) or now))
            title = f"[Daily IT] {label(problem.severity)} 계속({since}): {problem.title}"
        else:
            continue
        notifier.send(title, problem.detail, urgent=problem.severity == "critical")
        entry["notified_at"] = now.isoformat()
        sent.append(title)
        log(f"alert {key}: {problem.title} | {problem.detail}")
    for key in [k for k in known if k not in current]:
        if not findings.checked(key):
            continue  # unknown this run (Docker or the database is down): keep it open
        entry = known.pop(key)
        if key.startswith("briefing_missing:") and key != today:
            log(f"expired {key}")  # a new day: yesterday's missing briefing is not "recovered"
            continue
        if entry.get("notified_at"):
            since = _age(now - (_when(entry.get("first_seen")) or now))
            title = f"[Daily IT] 복구: {entry.get('title', key)}"
            notifier.send(title, f"{since} 만에 정상으로 돌아왔습니다", urgent=False)
            sent.append(title)
        log(f"cleared {key}")
    return sent


def open_docker(state: dict[str, Any], now: datetime, run: Runner) -> bool:
    """Start Docker Desktop, at most once per DOCKER_REOPEN (it takes a minute or two)."""
    opened = _when(state.get("docker_opened_at"))
    if opened is not None and now - opened < DOCKER_REOPEN:
        return False
    code, out = run(["open", "-a", "Docker"], 30)
    state["docker_opened_at"] = now.isoformat()
    log("started Docker Desktop" if code == 0 else f"could not start Docker Desktop: {out[:200]}")
    return code == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    default_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--root", type=Path, default=default_root, help="the live worktree")
    parser.add_argument(
        "--state", type=Path, help="state file (default ops/logs/watchdog-state.json)"
    )
    parser.add_argument("--dry-run", action="store_true", help="print the findings, send nothing")
    parser.add_argument("--test-notify", action="store_true", help="send one test message")
    args = parser.parse_args(argv)

    env = read_env(args.root / ".env")
    notifier = Notifier(env)
    if args.test_notify:
        delivered = notifier.send(
            "[Daily IT] 워치독 시험 알림", "이 알림이 보이면 푸시 설정이 끝났습니다", urgent=False
        )
        print(
            f"channels: {', '.join(notifier.channels()) or '-'}; "
            f"delivered: {', '.join(delivered) or '-'}"
        )
        return 0 if delivered else 1

    now = datetime.now(UTC)
    findings = inspect(env, now)
    problems = findings.problems
    if args.dry_run:
        for problem in problems:
            print(f"[{problem.severity}] {problem.key}: {problem.title} | {problem.detail}")
        print(f"{len(problems)} problem(s); channels: {', '.join(notifier.channels()) or '-'}")
        return 0

    state_path = args.state or args.root / "ops" / "logs" / "watchdog-state.json"
    state = load_state(state_path)
    if findings.docker_down and not findings.docker_app:
        open_docker(state, now, run_command)  # a running but stuck app gains nothing from `open`
    step(state, findings, now, notifier)
    beat = _when(state.get("heartbeat_at"))
    if beat is None or now - beat >= HEARTBEAT:
        summary = ", ".join(sorted(p.key for p in problems)) or "ok"
        log(f"heartbeat: {summary}; channels: {', '.join(notifier.channels()) or '-'}")
        state["heartbeat_at"] = now.isoformat()
    save_state(state_path, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
