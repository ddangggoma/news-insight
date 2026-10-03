"""Operator CLI: `news-insight sources seed|validate|promote|report`."""

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer
from sqlalchemy import select

from news_insight.collect.dead_letters import DeadLetterError, dismiss, list_open, retry
from news_insight.collect.models import FetchOutcome, SourceRuntime
from news_insight.collect.service import collect_source
from news_insight.config import get_settings
from news_insight.content.trends import metric_movers
from news_insight.db import session_scope
from news_insight.digest.claude import ClaudeCli, ClaudeClient
from news_insight.digest.service import generate_digest
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.scheduling.redis_guards import DomainRateLimiter, RateLimiter, get_redis
from news_insight.sources.autovalidate import auto_validate
from news_insight.sources.canary import run_canaries
from news_insight.sources.catalog import DEFAULT_CATALOG_PATH, load_catalog, seed_catalog
from news_insight.sources.enums import (
    STAGE_ORDER,
    SourceStatus,
    Track,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.ladder import CheckResult, LadderError, pause_source, resume_source
from news_insight.sources.models import Source
from news_insight.sources.portfolio import (
    REGION_FLOORS,
    TRACK_TARGETS,
    active_portfolio,
    build_report,
    region_capacity,
)
from news_insight.sources.service import (
    SourceNotFound,
    climb,
    get_source,
    probe_source,
    run_check,
    stage_counts,
)

app = typer.Typer(help="Daily IT Intelligence operations CLI", no_args_is_help=True)
sources_app = typer.Typer(help="Source registry and V0-V6 validation ladder", no_args_is_help=True)
app.add_typer(sources_app, name="sources")

collect_app = typer.Typer(help="Collection runs and schedule", no_args_is_help=True)
dlq_app = typer.Typer(help="Dead-letter queue", no_args_is_help=True)
app.add_typer(collect_app, name="collect")
app.add_typer(dlq_app, name="dlq")
trends_app = typer.Typer(help="Signal trends from metric snapshots", no_args_is_help=True)
app.add_typer(trends_app, name="trends")
digest_app = typer.Typer(
    help="Daily digest generated with the Claude CLI (05:00 KST)", no_args_is_help=True
)
app.add_typer(digest_app, name="digest")

KST = ZoneInfo("Asia/Seoul")
FAILED_OUTCOMES = (FetchOutcome.FAILED, FetchOutcome.DEAD_LETTERED)

CLIMBABLE = (ValidationStage.V0, ValidationStage.V1, ValidationStage.V2, ValidationStage.V3)


def _fetcher() -> SafeFetcher:
    return SafeFetcher.from_settings(get_settings())


def _limiter() -> RateLimiter:
    return DomainRateLimiter(get_redis(), per_minute=get_settings().domain_rate_per_minute)


def _claude() -> ClaudeClient:
    settings = get_settings()
    return ClaudeCli(
        executable=settings.claude_cli, timeout_seconds=settings.digest_timeout_seconds
    )


def _kst(moment: datetime | None) -> str:
    return moment.astimezone(KST).strftime("%m-%d %H:%M KST") if moment else "-"


def _fail(message: str, code: int = 2) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=code)


@sources_app.command("seed")
def seed(
    catalog: Annotated[Path, typer.Option(help="Catalog YAML path")] = DEFAULT_CATALOG_PATH,
) -> None:
    """Upsert catalog entries; identity changes reset validation."""
    with session_scope() as session:
        result = seed_catalog(session, load_catalog(catalog))
    typer.echo(
        f"created={len(result.created)} updated={len(result.updated)} reset={len(result.reset)}"
    )


@sources_app.command("validate")
def validate(
    key: str,
    until: Annotated[
        ValidationStage, typer.Option(help="Highest stage to attempt (V0-V3)")
    ] = ValidationStage.V3,
) -> None:
    """Climb the ladder from the current stage up to --until, stopping at the first failure."""
    if until not in CLIMBABLE:
        raise _fail("validate climbs V0-V3 only; use 'promote' for V6")
    try:
        with session_scope() as session, _fetcher() as fetcher:
            source = get_source(session, key)
            events = climb(session, source, fetcher=fetcher, now=datetime.now(UTC), until=until)
            lines = [
                f"{event.stage.value} {event.outcome.value}: {'; '.join(event.reasons) or 'ok'}"
                for event in events
            ]
            summary = (
                f"{source.key}: stage={source.validation_stage.value} status={source.status.value}"
            )
            failed = any(event.outcome is ValidationOutcome.FAILED for event in events)
    except (SourceNotFound, LadderError) as exc:
        raise _fail(str(exc)) from exc
    for line in lines:
        typer.echo(line)
    typer.echo(summary)
    if failed:
        raise typer.Exit(code=1)


@sources_app.command("promote")
def promote(key: str) -> None:
    """Run the V6 portfolio gate for a source that has passed V5."""
    try:
        with session_scope() as session, _fetcher() as fetcher:
            source = get_source(session, key)
            event = run_check(
                session, source, ValidationStage.V6, fetcher=fetcher, now=datetime.now(UTC)
            )
            line = f"V6 {event.outcome.value}: {'; '.join(event.reasons) or 'ok'}"
            passed = event.outcome is ValidationOutcome.PASSED
    except (SourceNotFound, LadderError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(line)
    if not passed:
        raise typer.Exit(code=1)


@sources_app.command("report")
def report() -> None:
    """Show active sources against track targets, region capacity and stage distribution."""
    with session_scope() as session:
        portfolio = build_report(active_portfolio(session))
        stages = stage_counts(session)
    typer.echo("Tracks (active/target)")
    for track, target in TRACK_TARGETS.items():
        typer.echo(f"  {track.value:<14} {portfolio.track_counts[track]:>3}/{target}")
    typer.echo("Regions (active/capacity, share vs floor)")
    for region, floor in REGION_FLOORS.items():
        counts = f"{portfolio.region_counts[region]:>3}/{region_capacity(region):<4}"
        typer.echo(
            f"  {region.value:<14} {counts}"
            f"{portfolio.region_share(region):6.1%} (floor {floor:.0%})"
        )
    typer.echo("Validation stages")
    for stage in STAGE_ORDER:
        typer.echo(f"  {stage.value:<14} {stages.get(stage, 0)}")


@sources_app.command("canary")
def canary() -> None:
    """Judge V4 for V3 candidates whose 24 h observation window is complete."""
    with session_scope() as session:
        lines = [
            f"{event.source.key}: V4 {event.outcome.value}: {'; '.join(event.reasons) or 'ok'}"
            for event in run_canaries(session, datetime.now(UTC))
        ]
    typer.echo("\n".join(lines) if lines else "no sources ready for V4 yet")


@sources_app.command("auto-validate")
def auto_validate_command(
    limit: Annotated[int, typer.Option(help="Maximum sources to climb in this run")] = 100,
) -> None:
    """Climb unverified candidates to V3 (public feeds/APIs pass V1 automatically, D17)."""
    with _fetcher() as fetcher:
        stats = auto_validate(session_scope, fetcher=fetcher, now=datetime.now(UTC), limit=limit)
    failed = " ".join(f"{stage}={count}" for stage, count in sorted(stats.failed.items()))
    typer.echo(
        f"checked={stats.checked} reached_v3={stats.reached_v3} errors={stats.errors}"
        + (f" failed: {failed}" if failed else "")
    )


@sources_app.command("pause")
def pause(key: str, reason: Annotated[str, typer.Option(help="Why the source is paused")]) -> None:
    """Stop collecting a source until it is resumed."""
    try:
        with session_scope() as session:
            pause_source(session, get_source(session, key), reason=reason)
    except (SourceNotFound, LadderError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"{key}: paused ({reason})")


@sources_app.command("resume")
def resume(key: str) -> None:
    """Resume a paused source (active if it holds V6, otherwise candidate)."""
    try:
        with session_scope() as session:
            source = get_source(session, key)
            resume_source(session, source)
            status = source.status.value
    except (SourceNotFound, LadderError) as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"{key}: resumed as {status}")


@collect_app.command("run")
def collect_run(key: str) -> None:
    """Collect one source now (ignores the schedule, honours the domain budget)."""
    try:
        with session_scope() as session, _fetcher() as fetcher:
            source = get_source(session, key)
            run = collect_source(
                session, source, fetcher=fetcher, limiter=_limiter(), now=datetime.now(UTC)
            )
            line = (
                f"{key}: {run.outcome.value} http={run.http_status} new={run.items_new} "
                f"updated={run.items_updated} unchanged={run.items_unchanged}"
            )
            if run.error_code:
                line += f" error={run.error_code}"
            failed = run.outcome in FAILED_OUTCOMES
    except SourceNotFound as exc:
        raise _fail(str(exc)) from exc
    typer.echo(line)
    if failed:
        raise typer.Exit(code=1)


@collect_app.command("status")
def collect_status() -> None:
    """Show each scheduled source with its next poll, interval and failure streak."""
    with session_scope() as session:
        rows = session.execute(
            select(Source.key, SourceRuntime)
            .join(SourceRuntime, SourceRuntime.source_id == Source.id)
            .order_by(SourceRuntime.next_due_at)
        ).all()
        lines = [
            f"{key:<24} next={_kst(runtime.next_due_at)} every={runtime.interval_seconds // 60}m "
            f"failures={runtime.consecutive_failures} last_success={_kst(runtime.last_success_at)}"
            for key, runtime in rows
        ]
    typer.echo("\n".join(lines) if lines else "no sources scheduled yet")


@dlq_app.command("list")
def dlq_list(limit: Annotated[int, typer.Option(help="Maximum entries")] = 50) -> None:
    """List unresolved dead letters, newest first."""
    with session_scope() as session:
        lines = []
        for letter in list_open(session, limit=limit):
            source = session.get(Source, letter.source_id)
            key = source.key if source is not None else f"source#{letter.source_id}"
            lines.append(
                f"#{letter.id} {key} {letter.error_code} attempts={letter.attempts} "
                f"{_kst(letter.created_at)} {letter.error_message[:80]}"
            )
    typer.echo("\n".join(lines) if lines else "dead-letter queue is empty")


@dlq_app.command("retry")
def dlq_retry(dead_letter_id: int) -> None:
    """Resolve a dead letter and make its source due immediately."""
    try:
        with session_scope() as session:
            retry(session, dead_letter_id, now=datetime.now(UTC))
    except DeadLetterError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"#{dead_letter_id}: retried")


@dlq_app.command("dismiss")
def dlq_dismiss(dead_letter_id: int) -> None:
    """Resolve a dead letter without retrying."""
    try:
        with session_scope() as session:
            dismiss(session, dead_letter_id, now=datetime.now(UTC))
    except DeadLetterError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"#{dead_letter_id}: dismissed")


def _probe_line(source: Source, results: list[tuple[ValidationStage, CheckResult]]) -> str:
    marks = " ".join(
        f"{stage.value}:{'ok' if result.passed else 'FAIL'}" for stage, result in results
    )
    problems = "; ".join(
        f"{stage.value} {reason}"
        for stage, result in results
        if stage is not ValidationStage.V1
        for reason in result.reasons
    )
    line = f"{source.key:<30} {source.track.value:<11} {source.region.value:<13} {marks}"
    return f"{line} | {problems}" if problems else line


def _ready(results: list[tuple[ValidationStage, CheckResult]]) -> bool:
    return all(result.passed for stage, result in results if stage is not ValidationStage.V1)


@sources_app.command("probe")
def probe(key: str) -> None:
    """Dry-run V0-V3 for a registered source (nothing is recorded)."""
    try:
        with session_scope() as session, _fetcher() as fetcher:
            source = get_source(session, key)
            line = _probe_line(source, probe_source(source, fetcher=fetcher, now=datetime.now(UTC)))
    except SourceNotFound as exc:
        raise _fail(str(exc)) from exc
    typer.echo(line)


@sources_app.command("probe-catalog")
def probe_catalog(
    catalog: Annotated[Path, typer.Option(help="Catalog YAML path")] = DEFAULT_CATALOG_PATH,
    track: Annotated[Track | None, typer.Option(help="Only this track")] = None,
) -> None:
    """Dry-run V0, V2 and V3 for catalog entries before seeding (V1 shown for reference)."""
    entries = [
        entry for entry in load_catalog(catalog).sources if track is None or entry.track is track
    ]
    totals: Counter[Track] = Counter()
    ready_tracks: Counter[Track] = Counter()
    ready_regions: Counter[str] = Counter()
    now = datetime.now(UTC)
    with _fetcher() as fetcher:
        for entry in entries:
            source = Source(
                **entry.model_dump(),
                validation_stage=ValidationStage.UNVERIFIED,
                status=SourceStatus.CANDIDATE,
            )
            results = probe_source(source, fetcher=fetcher, now=now)
            typer.echo(_probe_line(source, results))
            totals[entry.track] += 1
            if _ready(results):
                ready_tracks[entry.track] += 1
                ready_regions[entry.region.value] += 1
    typer.echo(
        "Ready (V0+V2+V3) by track: "
        + ", ".join(
            f"{name.value} {ready_tracks[name]}/{totals[name]}" for name in Track if totals[name]
        )
    )
    typer.echo(
        "Ready by region: "
        + ", ".join(f"{name} {count}" for name, count in sorted(ready_regions.items()))
    )
    if sum(ready_tracks.values()) < len(entries):
        raise typer.Exit(code=1)


@trends_app.command("movers")
def movers(
    metric: Annotated[str, typer.Option(help="Metric key, e.g. stars, points, likes")] = "stars",
    days: Annotated[int, typer.Option(help="Window in days")] = 1,
    track: Annotated[Track | None, typer.Option(help="Only this track")] = None,
    limit: Annotated[int, typer.Option(help="Maximum rows")] = 20,
) -> None:
    """Items whose metric grew the most over the window."""
    with session_scope() as session:
        rows = metric_movers(
            session,
            metric=metric,
            window=timedelta(days=days),
            now=datetime.now(UTC),
            track=track,
            limit=limit,
        )
        lines = [
            f"{row.delta:+8d} {row.current:>9d}  {row.item.title}  {row.item.url}" for row in rows
        ]
    typer.echo("\n".join(lines) if lines else "no movers yet (needs two snapshots per item)")


@digest_app.command("run")
def digest_run(
    on: Annotated[
        str | None, typer.Option("--date", help="Publication date YYYY-MM-DD (KST)")
    ] = None,
    model: Annotated[
        str | None, typer.Option(help="Claude model alias (default: DIGEST_MODEL)")
    ] = None,
) -> None:
    """Summarise the previous KST day's items and publish the digest (fallback on failure)."""
    now = datetime.now(UTC)
    digest_date = date.fromisoformat(on) if on else now.astimezone(KST).date()
    with session_scope() as session:
        digest = generate_digest(
            session,
            digest_date=digest_date,
            now=now,
            client=_claude(),
            model=model or get_settings().digest_model,
        )
        line = (
            f"{digest.digest_date} v{digest.version} {digest.status.value} "
            f"items={digest.item_count} model={digest.model or '-'}"
        )
        if digest.cost_usd is not None:
            line += f" cost=${digest.cost_usd:.3f}"
        if digest.error:
            line += f" error={digest.error}"
    typer.echo(line)
