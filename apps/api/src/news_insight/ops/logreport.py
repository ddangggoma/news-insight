"""Log analysis across the stack (host-side): what failed, how often, since when.

Sources: the containers' Docker logs (`docker logs --since`) and the host job logs in
`ops/logs/*.log` (cards, digest, backup). Every line becomes an event:

- our JSON lines (`observability.JsonFormatter`): level, logger, message, request fields;
- Caddy's JSON access/error lines;
- plain text: Python tracebacks (folded into one event), Next.js errors, anything with
  ERROR/Exception/Traceback.

Errors and warnings are grouped by a signature (numbers, ids, quoted values and links
replaced), so one recurring fault is one row with a count, first/last time and a sample.
API access lines give per-route status counts and latency percentiles; Celery lines give task
failures; card runs give ready/failed totals.
"""

import json
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

CONTAINERS = ("api", "worker", "scheduler", "web", "caddy", "postgres", "redis")
HOST_LOGS = ("cards", "digest", "backup")
LEVELS = {"critical": 50, "fatal": 50, "error": 40, "warning": 30, "warn": 30, "info": 20}

TS_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s")
TEXT_ERROR = re.compile(
    r"\b(ERROR|CRITICAL|FATAL|Exception|Traceback|Error:)|⨯|\bpanic:", re.IGNORECASE
)
TEXT_WARNING = re.compile(r"\bWARN(ING)?\b")
EXCEPTION_LINE = re.compile(r"^([\w.]+(?:Error|Exception|Exit|Interrupt|Timeout|Shutdown)\b.*)$")
# lines that continue a traceback: indented frames, chained-exception notes, SQLAlchemy's
# "(Background on this error…)", rich's boxed frames (CLI logs before 2026-10-05)
TRACE_CONTINUES = re.compile(
    r"^(\s|The above exception|During handling|\(Background on this error|\[SQL:|\[parameters:|[╭╰│├─])"
)
TRACE_STARTS = re.compile(r"^(Traceback|╭─+ Traceback|ERROR:\s+Exception in ASGI application)")

# signature normalisation: what varies between occurrences of one fault
_NORMALISE = (
    # Postgres prefixes every line with its own time and pid
    (re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)? \w+ \[\d+\] "), ""),
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<uuid>"),
    (re.compile(r"\b[0-9a-f]{12,}\b"), "<hex>"),
    # quoted values vary; short double-quoted names (a constraint, a table) say what failed
    (re.compile(r"'[^']{0,200}'|\"[^\"]{41,200}\""), "<str>"),
    (re.compile(r"\d+(\.\d+)?"), "<n>"),
    (re.compile(r"\s+"), " "),
)
ROUTE_ID = re.compile(r"/\d+(?=/|$)")


@dataclass
class Event:
    service: str
    ts: datetime | None
    level: str  # error | warning | info
    logger: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


def signature(message: str) -> str:
    text = message.strip().splitlines()[0] if message.strip() else ""
    for pattern, replacement in _NORMALISE:
        text = pattern.sub(replacement, text)
    return text.strip()[:180]


def _ts(value: Any) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def parse_lines(service: str, lines: Iterable[str]) -> Iterator[Event]:
    """Events from one source; consecutive traceback lines fold into the event they explain."""
    trace: list[str] = []
    trace_ts: datetime | None = None
    last_ts: datetime | None = None  # host job lines carry no time: use the latest JSON line's
    in_sql = False

    def flush() -> Iterator[Event]:
        nonlocal trace, trace_ts, in_sql
        if trace:
            last = next(
                (ln for ln in reversed(trace) if EXCEPTION_LINE.match(ln.strip().strip("│ "))),
                trace[-1],
            )
            yield Event(
                service, trace_ts, "error", "traceback", last.strip()[:500], {"trace": trace[-12:]}
            )
        trace, trace_ts, in_sql = [], None, False

    for raw in lines:
        line = raw.rstrip("\n")
        stamp = None
        match = TS_PREFIX.match(line)
        if match:  # `docker logs --timestamps`
            stamp, line = _ts(match.group(1)), line[match.end() :]
        stamp = stamp or last_ts
        if not line.strip():
            continue
        if line.startswith("{"):
            try:
                record = json.loads(line)
            except ValueError:
                record = None
            if isinstance(record, dict):
                yield from flush()
                event = _json_event(service, record, stamp)
                last_ts = event.ts or last_ts
                yield event
                continue
        last_ts = stamp or last_ts
        if TRACE_STARTS.match(line) or (
            trace and (in_sql or TRACE_CONTINUES.match(line) or EXCEPTION_LINE.match(line.strip()))
        ):
            if not trace:
                trace_ts = stamp
            trace.append(line)
            # SQLAlchemy prints the failing statement unindented, up to "(Background on …)"
            if "[SQL:" in line:
                in_sql = True
            if line.startswith("(Background on this error"):
                in_sql = False
            continue
        yield from flush()
        if TEXT_ERROR.search(line):
            yield Event(service, stamp, "error", "text", line.strip()[:500])
        elif TEXT_WARNING.search(line):
            yield Event(service, stamp, "warning", "text", line.strip()[:500])
        else:
            yield Event(service, stamp, "info", "text", line.strip()[:500])
    yield from flush()


def _json_event(service: str, record: dict[str, Any], stamp: datetime | None) -> Event:
    level = str(record.get("level", "info")).lower()
    level = (
        "error"
        if LEVELS.get(level, 20) >= 40
        else ("warning" if LEVELS.get(level, 20) >= 30 else "info")
    )
    message = str(record.get("msg", ""))
    if record.get("exc"):
        tail = [ln for ln in str(record["exc"]).splitlines() if ln.strip()]
        message = f"{message}: {tail[-1].strip()}" if tail else message
    return Event(
        service=str(record.get("service") or service),
        ts=_ts(record.get("ts")) or stamp,
        level=level,
        logger=str(record.get("logger", "")),
        message=message,
        data=record,
    )


def docker_lines(container: str, since: timedelta) -> list[str]:
    seconds = int(since.total_seconds())
    try:
        done = subprocess.run(
            ["docker", "logs", "--timestamps", "--since", f"{seconds}s", container],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return (done.stdout + done.stderr).splitlines()


def host_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


@dataclass
class Group:
    service: str
    level: str
    signature: str
    count: int = 0
    first: datetime | None = None
    last: datetime | None = None
    sample: str = ""


@dataclass
class Report:
    since: datetime
    until: datetime
    lines: Counter[str] = field(default_factory=Counter)
    errors: Counter[str] = field(default_factory=Counter)
    warnings: Counter[str] = field(default_factory=Counter)
    groups: list[Group] = field(default_factory=list)
    routes: dict[str, dict[str, Any]] = field(default_factory=dict)
    tasks: dict[str, dict[str, int]] = field(default_factory=dict)
    card_runs: dict[str, int] = field(default_factory=dict)


def analyse(events: Iterable[Event], *, since: datetime, until: datetime) -> Report:
    report = Report(since=since, until=until)
    groups: dict[tuple[str, str, str], Group] = {}
    latency: dict[str, list[int]] = defaultdict(list)
    statuses: dict[str, Counter[str]] = defaultdict(Counter)
    tasks: dict[str, Counter[str]] = defaultdict(Counter)
    runs: Counter[str] = Counter()
    for event in events:
        if event.ts is not None and event.ts < since:
            continue
        report.lines[event.service] += 1
        data = event.data
        if event.logger == "news_insight.http" and data.get("path"):
            route = ROUTE_ID.sub("/:id", str(data["path"]))
            status = int(data.get("status") or 0)
            statuses[route][f"{status // 100}xx"] += 1
            if isinstance(data.get("ms"), int):
                latency[route].append(data["ms"])
        if event.logger.startswith("celery.app.trace"):
            name = re.search(r"Task ([\w.]+)\[", event.message)
            if name:
                outcome = (
                    "failed"
                    if " raised " in event.message or event.level == "error"
                    else ("retry" if "retry" in event.message.lower() else "ok")
                )
                tasks[name.group(1)][outcome] += 1
        if event.logger == "news_insight.cards.service" and event.message == "card run":
            for key in ("ready", "failed", "soft"):
                runs[key] += int(data.get(key) or 0)
            runs["runs"] += 1
        if event.level in ("error", "warning"):
            (report.errors if event.level == "error" else report.warnings)[event.service] += 1
            group_key = (event.service, event.level, signature(event.message))
            group = groups.setdefault(
                group_key,
                Group(event.service, event.level, group_key[2], sample=event.message[:400]),
            )
            group.count += 1
            if event.ts is not None:
                group.first = min(group.first or event.ts, event.ts)
                group.last = max(group.last or event.ts, event.ts)
    report.groups = sorted(groups.values(), key=lambda g: (g.level != "error", -g.count))
    for route, values in latency.items():
        ordered = sorted(values)
        report.routes[route] = {
            "count": len(ordered),
            "p50": int(median(ordered)),
            "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
            "max": ordered[-1],
            **dict(statuses[route]),
        }
    for route, counts in statuses.items():
        report.routes.setdefault(route, {"count": sum(counts.values()), **dict(counts)})
    report.tasks = {name: dict(counts) for name, counts in tasks.items()}
    report.card_runs = dict(runs)
    return report


def collect(root: Path, since: timedelta) -> list[Event]:
    events: list[Event] = []
    for name in CONTAINERS:
        events.extend(parse_lines(name, docker_lines(f"news-insight-{name}-1", since)))
        # logs of containers a deploy replaced (scripts/deploy.sh archives them)
        for archived in sorted((root / "ops" / "logs" / "containers").glob(f"{name}-*.log")):
            events.extend(parse_lines(name, host_lines(archived)))
    for name in HOST_LOGS:
        events.extend(
            parse_lines(f"host:{name}", host_lines(root / "ops" / "logs" / f"{name}.log"))
        )
    return events


def render(report: Report, *, top: int = 25) -> str:
    def when(moment: datetime | None) -> str:
        return moment.astimezone(UTC).strftime("%m-%d %H:%M") if moment else "-"

    out = [
        f"# Log report {when(report.since)} → {when(report.until)} UTC",
        "",
        "## By service",
        "",
        "| service | lines | errors | warnings |",
        "|---|---:|---:|---:|",
    ]
    for service in sorted(report.lines, key=lambda s: -report.errors[s]):
        out.append(
            f"| {service} | {report.lines[service]} | {report.errors[service]} | {report.warnings[service]} |"
        )
    out += [
        "",
        f"## Top {top} error and warning signatures",
        "",
        "| level | service | count | first | last | signature |",
        "|---|---|---:|---|---|---|",
    ]
    for group in report.groups[:top]:
        sig = group.signature.replace("|", "\\|")
        out.append(
            f"| {group.level} | {group.service} | {group.count} | {when(group.first)} | {when(group.last)} | {sig} |"
        )
    if report.routes:
        out += [
            "",
            "## API routes (slowest p95 first)",
            "",
            "| route | count | 2xx | 4xx | 5xx | p50 ms | p95 ms | max ms |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for route, row in sorted(report.routes.items(), key=lambda kv: -int(kv[1].get("p95", 0)))[
            :top
        ]:
            out.append(
                f"| {route} | {row['count']} | {row.get('2xx', 0)} | {row.get('4xx', 0)} | {row.get('5xx', 0)} "
                f"| {row.get('p50', '-')} | {row.get('p95', '-')} | {row.get('max', '-')} |"
            )
    if report.tasks:
        out += ["", "## Celery tasks", "", "| task | ok | retry | failed |", "|---|---:|---:|---:|"]
        for name, counts in sorted(report.tasks.items(), key=lambda kv: -kv[1].get("failed", 0)):
            out.append(
                f"| {name} | {counts.get('ok', 0)} | {counts.get('retry', 0)} | {counts.get('failed', 0)} |"
            )
    if report.card_runs:
        runs = report.card_runs
        out += [
            "",
            "## Card runs",
            "",
            f"runs {runs.get('runs', 0)}, ready {runs.get('ready', 0)}, failed {runs.get('failed', 0)}, kept with loss {runs.get('soft', 0)}",
        ]
    return "\n".join(out) + "\n"
