"""Operator CLI: `news-insight sources seed|validate|promote|report`."""

import fcntl
import sys
import tempfile
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.cards.engines import (
    AgyEngine,
    CodexEngine,
    EngineError,
    MeteredEngine,
    QwenEngine,
)
from news_insight.cards.models import CardRun, CardStatus, ItemCard
from news_insight.cards.service import CardPolicy, pending_count, record_run, run_cards
from news_insight.collect.dead_letters import DeadLetterError, dismiss, list_open, retry
from news_insight.collect.models import FetchOutcome, SourceRuntime
from news_insight.collect.service import collect_source
from news_insight.config import Settings, get_settings
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
from news_insight.sources.quality import run_quality
from news_insight.sources.service import (
    SourceNotFound,
    climb,
    get_source,
    probe_source,
    run_check,
    stage_counts,
)
from news_insight.stories.service import Thresholds, cluster

# plain tracebacks, not rich boxes: host job logs stay one JSON line per event plus the trace
app = typer.Typer(
    help="Daily IT Intelligence operations CLI",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


@app.callback()
def _setup() -> None:
    """JSON logs on stderr for host jobs (launchd keeps them in ops/logs)."""
    from news_insight.observability import configure_logging

    configure_logging("cli")


sources_app = typer.Typer(help="Source registry and V0-V6 validation ladder", no_args_is_help=True)
app.add_typer(sources_app, name="sources")

collect_app = typer.Typer(help="Collection runs and schedule", no_args_is_help=True)
dlq_app = typer.Typer(help="Dead-letter queue", no_args_is_help=True)
app.add_typer(collect_app, name="collect")
app.add_typer(dlq_app, name="dlq")
trends_app = typer.Typer(help="Signal trends from metric snapshots", no_args_is_help=True)
app.add_typer(trends_app, name="trends")
daily_app = typer.Typer(
    help="Daily briefing: 04:40 freeze, 05:00 gated immutable publication", no_args_is_help=True
)
app.add_typer(daily_app, name="daily")
audio_app = typer.Typer(help="Spoken daily briefing (plan 13 A1).", no_args_is_help=True)
app.add_typer(audio_app, name="audio")
periodic_app = typer.Typer(help="Weekly and monthly briefings (plan 13 C4).", no_args_is_help=True)
app.add_typer(periodic_app, name="periodic")
stories_app = typer.Typer(
    help="Issue clustering (exact/near/event) and cross-track identifiers", no_args_is_help=True
)
app.add_typer(stories_app, name="stories")
cards_app = typer.Typer(
    help="Korean cards: Antigravity CLI first, local Qwen when its quota is spent",
    no_args_is_help=True,
)
app.add_typer(cards_app, name="cards")
digest_app = typer.Typer(
    help="Daily digest generated with the Claude CLI (05:00 KST)", no_args_is_help=True
)
app.add_typer(digest_app, name="digest")
taxonomy_app = typer.Typer(
    help="Taxonomy migrations, schemes and nodes (plan 15)", no_args_is_help=True
)
app.add_typer(taxonomy_app, name="taxonomy")
tech_app = typer.Typer(
    help="Technology registry (third level of the taxonomy)", no_args_is_help=True
)
app.add_typer(tech_app, name="technologies")
companies_app = typer.Typer(help="Company registry and card company tags", no_args_is_help=True)
app.add_typer(companies_app, name="companies")
ops_app = typer.Typer(help="Operational health checks and alerts", no_args_is_help=True)
app.add_typer(ops_app, name="ops")
users_app = typer.Typer(help="Site accounts: admin bootstrap and recovery", no_args_is_help=True)
app.add_typer(users_app, name="users")

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


def _card_engines(qwen_only: bool) -> tuple[list[MeteredEngine], QwenEngine]:
    """Metered engines in order of use (Codex, Antigravity) and the local Qwen fallback."""
    settings = get_settings()
    metered: list[MeteredEngine] = []
    if not qwen_only and settings.card_codex_enabled:
        home = Path(settings.codex_home or Path.home() / ".codex").expanduser()
        metered.append(
            CodexEngine(
                executable=settings.codex_cli,
                model=settings.card_codex_model or None,
                timeout_seconds=settings.card_timeout_seconds,
                sessions_dir=home / "sessions",
            )
        )
    if not qwen_only:
        metered.append(
            AgyEngine(
                executable=settings.agy_cli,
                model=settings.card_agy_model,
                timeout_seconds=settings.card_timeout_seconds,
            )
        )
    qwen = QwenEngine(
        base_url=settings.lm_studio_url,
        model=settings.lm_studio_model,
        timeout_seconds=settings.card_timeout_seconds * 2,
    )
    return metered, qwen


def _scheduled_claude(settings: Settings) -> bool:
    """Claude joins a scheduled run while enabled (or before `card_claude_until`), outside the
    quiet hours and below the daily card cap."""
    from news_insight.cards.service import claude_cards_today, in_quiet_hours

    now = datetime.now(UTC)
    try:
        until = (
            datetime.fromisoformat(settings.card_claude_until)
            if settings.card_claude_until
            else None
        )
    except ValueError:
        until = None
    enabled = settings.card_claude or (until is not None and now < until)
    if not enabled or in_quiet_hours(settings.card_claude_quiet_hours, now):
        return False
    with session_scope() as session:
        return claude_cards_today(session, now) < settings.card_claude_daily_cap


def _judge_engine() -> MeteredEngine | None:
    """First metered engine above its reserve (story-merge judge, evaluations)."""
    settings = get_settings()
    metered, _ = _card_engines(False)
    for engine in metered:
        try:
            quota = engine.usage()
        except EngineError:
            continue
        if quota.usable(
            min_weekly=settings.card_agy_min_weekly, min_five_hour=settings.card_agy_min_five_hour
        ):
            return engine
    return None


def _kst(moment: datetime | None) -> str:
    return moment.astimezone(KST).strftime("%m-%d %H:%M KST") if moment else "-"


def _fail(message: str, code: int = 2) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=code)


@sources_app.command("seed")
def seed(
    catalog: Annotated[Path, typer.Option(help="Catalog YAML path")] = DEFAULT_CATALOG_PATH,
    prune: Annotated[
        bool, typer.Option(help="Retire registered sources that are no longer in the catalog")
    ] = False,
) -> None:
    """Upsert catalog entries; identity changes reset validation."""
    with session_scope() as session:
        result = seed_catalog(session, load_catalog(catalog), prune=prune)
    typer.echo(
        f"created={len(result.created)} updated={len(result.updated)} reset={len(result.reset)}"
        f" retired={len(result.retired)} revived={len(result.revived)}"
    )


@sources_app.command("retire")
def retire(
    key: str,
    reason: Annotated[str, typer.Option(help="Why the source is retired")],
) -> None:
    """Stop collecting a source for good (seeding it again revives it)."""
    from news_insight.sources.ladder import retire_source

    try:
        with session_scope() as session:
            retire_source(session, get_source(session, key), reason=reason)
    except SourceNotFound as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"{key}: retired ({reason})")


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


@sources_app.command("quality")
def quality_command(
    dry_run: Annotated[bool, typer.Option(help="Report without pausing or promoting")] = False,
) -> None:
    """V5/V6: pause low-relevance sources, promote high-relevance V4 sources (7-day cards)."""
    with session_scope() as session:
        run = run_quality(session, now=datetime.now(UTC), apply=not dry_run)
    typer.echo(
        f"judged={run.judged} paused={len(run.paused)} passed_v5={len(run.passed_v5)} "
        f"promoted_v6={len(run.promoted_v6)} track_full={len(run.track_full)}"
        + (" (dry run)" if dry_run else "")
    )
    for label, keys in (("paused", run.paused), ("promoted", run.promoted_v6)):
        if keys:
            typer.echo(f"  {label}: {', '.join(keys[:40])}{' …' if len(keys) > 40 else ''}")


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
        f"{stage.value} {reason}" for stage, result in results for reason in result.reasons
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


CARDS_LOCK = Path(tempfile.gettempdir()) / "news-insight-cards.lock"


@cards_app.command("run")
def cards_run(
    budget: Annotated[int | None, typer.Option(help="Time budget in seconds")] = None,
    qwen_only: Annotated[bool, typer.Option(help="Skip Codex and Antigravity; local Qwen")] = False,
    claude: Annotated[
        bool, typer.Option(help="Claude Code instead of Codex and Antigravity (Qwen alongside)")
    ] = False,
) -> None:
    """Generate Korean cards for pending items (host-side; launchd runs it every 10 minutes)."""
    settings = get_settings()
    with CARDS_LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            typer.echo("another card run is active; skipping")
            return
        metered, local = _card_engines(qwen_only)
        if claude or (not qwen_only and _scheduled_claude(settings)):
            from news_insight.cards.engines import ClaudeEngine

            cli = ClaudeCli(
                executable=settings.claude_cli, timeout_seconds=settings.card_timeout_seconds
            )
            # ahead of Codex and Antigravity; a usage-limit error moves the run down the chain
            metered = [ClaudeEngine(cli=cli, model=settings.card_claude_model), *metered]
        # Qwen only after every metered engine is down to its reserve (card_qwen_fallback)
        qwen = local if qwen_only or settings.card_qwen_fallback else None
        policy = CardPolicy(
            agy_batch=settings.card_agy_batch,
            agy_parallel=settings.card_agy_parallel,
            codex_batch=settings.card_codex_batch,
            codex_parallel=settings.card_codex_parallel,
            claude_batch=settings.card_claude_batch,
            claude_parallel=settings.card_claude_parallel,
            qwen_batch=settings.card_qwen_batch,
            qwen_parallel=settings.card_qwen_parallel,
            min_weekly=settings.card_agy_min_weekly,
            min_five_hour=settings.card_agy_min_five_hour,
            time_budget_seconds=float(budget or settings.card_time_budget_seconds),
            unvalidated_daily_cap=settings.card_unvalidated_daily_cap or None,
            cap_bypass_dx=settings.card_cap_bypass_dx,
        )
        started = datetime.now(UTC)
        stats = run_cards(
            session_scope,
            metered=metered,
            qwen=qwen,
            policy=policy,
            qwen_alongside=settings.card_qwen_alongside and not qwen_only,
        )
        record_run(session_scope, started, stats)
    batches = " ".join(f"{name}={count}" for name, count in sorted(stats.batches.items()))
    typer.echo(
        f"ready={stats.ready} failed={stats.failed} kept_with_loss={stats.soft} "
        f"reused={stats.reused} "
        f"classified={stats.classified} "
        f"batches: {batches or '-'} "
        f"quota={stats.quota or '-'}"
    )
    for note in stats.notes:
        typer.echo(f"  note: {note}")


@cards_app.command("triage")
def cards_triage(
    embed_limit: Annotated[int, typer.Option(help="Titles to embed this run")] = 2000,
    score_limit: Annotated[int, typer.Option(help="Items to score this run")] = 20000,
) -> None:
    """Embed new titles and score items for carding (plan 16 #3; host: LM Studio bge-m3)."""
    from news_insight.cards.triage import embed_titles, score_pending
    from news_insight.taxonomy.embeddings import embedder

    settings = get_settings()
    now = datetime.now(UTC)
    with session_scope() as session:
        embedded = embed_titles(
            session,
            embedder(),
            model=settings.lm_studio_embedding_model,
            now=now,
            limit=embed_limit,
        )
    with session_scope() as session:
        scored = score_pending(session, now=now, limit=score_limit)
    typer.echo(f"embedded={embedded} scored={scored}")


@cards_app.command("dedup")
def cards_dedup() -> None:
    """Duplicate keys and roots for items stored before item_dedup existed (one-off backfill,
    2026-10-10), then copy group cards so repeats leave the queue."""
    from news_insight.cards.service import reuse_cards
    from news_insight.content.duplicates import backfill

    now = datetime.now(UTC)
    with session_scope() as session:
        stats = backfill(session, now=now)
    copied = 0
    while True:
        with session_scope() as session:
            done = reuse_cards(session, now=now, limit=5000)
        copied += len(done)
        if len(done) < 5000:
            break
    kinds = " ".join(f"{kind}={n}" for kind, n in sorted(stats.by_kind.items()))
    typer.echo(
        f"keyed={stats.keyed} repeats={stats.repeats} ({kinds or '-'}) "
        f"links_recovered={stats.links} cards_copied={copied}"
    )


@cards_app.command("embed")
def cards_embed(
    limit: Annotated[int, typer.Option(help="Cards to embed this run")] = 2000,
) -> None:
    """Embed ready cards for questions over the corpus (plan 16 #1; host: LM Studio bge-m3)."""
    from news_insight.ask.service import embed_cards
    from news_insight.taxonomy.embeddings import embedder

    settings = get_settings()
    with session_scope() as session:
        done = embed_cards(
            session,
            embedder(),
            model=settings.lm_studio_embedding_model,
            now=datetime.now(UTC),
            limit=limit,
        )
    typer.echo(f"embedded={done}")


@cards_app.command("deals")
def cards_deals(
    limit: Annotated[int, typer.Option(help="Cards to read this run")] = 36,
    night: Annotated[bool, typer.Option(help="Only between 00:00 and 06:00 KST")] = False,
) -> None:
    """Extract investments, acquisitions and partnerships with the local Qwen (plan 16 #8)."""
    from news_insight.deals.extract import lm_studio_chat, scan
    from news_insight.public.periods import KST

    now = datetime.now(UTC)
    if night and not 0 <= now.astimezone(KST).hour < 6:
        typer.echo("deals: daytime, skipped (the local Qwen writes cards by day)")
        return
    settings = get_settings()
    chat = lm_studio_chat(settings.lm_studio_url, settings.lm_studio_model)
    with session_scope() as session:
        stats = scan(session, chat, model=settings.lm_studio_model, now=now, limit=limit)
    typer.echo(
        f"deals: read={stats.read} found={stats.deals} failed_batches={stats.failed_batches}"
    )


@cards_app.command("triage-train")
def cards_triage_train() -> None:
    """Fit the carding-priority model on recent cards (nightly; plan 16 #3)."""
    from news_insight.cards.triage import train

    with session_scope() as session:
        result = train(session, now=datetime.now(UTC))
    typer.echo(
        "not enough labelled cards"
        if result is None
        else f"model {result.model_id} auc={result.auc} samples={result.samples}"
    )


@cards_app.command("retry-failed")
def cards_retry_failed(
    days: Annotated[int, typer.Option(help="Items first seen in the last N days")] = 7,
) -> None:
    """Give cards that failed the preservation check one more attempt (with the lost facts named).

    That attempt is the last: if a fact is still missing the card is kept with a note."""
    from sqlalchemy import update

    from news_insight.cards.service import LOST, MAX_ATTEMPTS
    from news_insight.content.models import Item

    since = datetime.now(UTC) - timedelta(days=days)
    with session_scope() as session:
        ids = select(Item.id).where(Item.first_seen_at >= since)
        result = session.execute(
            update(ItemCard)
            .where(
                ItemCard.status == CardStatus.FAILED,
                ItemCard.error.like(f"{LOST}%"),
                ItemCard.item_id.in_(ids),
            )
            .values(attempts=MAX_ATTEMPTS - 1)
            .execution_options(synchronize_session=False)
        )
    typer.echo(f"requeued={getattr(result, 'rowcount', 0)}")


@cards_app.command("status")
def cards_status() -> None:
    """Pending, ready and failed card counts and the latest run."""
    with session_scope() as session:
        counts = dict(
            session.execute(select(ItemCard.status, func.count()).group_by(ItemCard.status))
            .tuples()
            .all()
        )
        from news_insight.cards.service import classify_pending_count

        pending = pending_count(session)
        reclassify = classify_pending_count(session)
        last = session.scalars(select(CardRun).order_by(CardRun.id.desc()).limit(1)).first()
        from news_insight.content.models import ItemDedup

        repeats = dict(
            session.execute(
                select(ItemDedup.matched_by, func.count())
                .where(ItemDedup.duplicate_of.is_not(None))
                .group_by(ItemDedup.matched_by)
            )
            .tuples()
            .all()
        )
        line = (
            f"pending={pending} reclassify={reclassify} ready={counts.get(CardStatus.READY, 0)} "
            f"failed={counts.get(CardStatus.FAILED, 0)} "
            f"repeats={sum(repeats.values())} ("
            + " ".join(f"{kind}={n}" for kind, n in sorted(repeats.items()))
            + ")"
        )
        if last is not None:
            line += (
                f"\nlast run {_kst(last.started_at)}: ready={last.ready} failed={last.failed} "
                f"classified={last.classified} batches={last.batches} quota={last.quota}"
            )
    typer.echo(line)


@stories_app.command("run")
def stories_run(
    limit: Annotated[int, typer.Option(help="Maximum items to cluster")] = 5000,
    near: Annotated[float, typer.Option(help="Near-duplicate MinHash threshold")] = 0.45,
    event: Annotated[float, typer.Option(help="Same-event MinHash threshold")] = 0.35,
) -> None:
    """Attach carded items to stories (exact duplicate, near duplicate, same event or new)."""
    stats = cluster(
        session_scope,
        now=datetime.now(UTC),
        limit=limit,
        thresholds=Thresholds(near=near, event=event),
    )
    relations = " ".join(f"{k}={v}" for k, v in sorted(stats.by_relation.items()))
    typer.echo(f"processed={stats.processed} {relations or '-'} refs={stats.refs}")


@stories_app.command("semantic")
def stories_semantic(
    since_minutes: Annotated[
        int,
        typer.Option(help="Look for neighbours of items embedded in the last N minutes (0 = all)"),
    ] = 60,
    max_judged: Annotated[int, typer.Option(help="Most candidate pairs to judge per run")] = 200,
    embed_limit: Annotated[int, typer.Option(help="Most titles to embed per run")] = 500,
) -> None:
    """Merge stories that report one event in other words or languages (bge-m3 + LLM judge, CLU-1).

    Host-side: needs LM Studio (embeddings) and Codex or Antigravity (judge); after `cards run`."""
    from news_insight.stories.semantic import embed_pending, lm_studio_embed, run

    settings = get_settings()
    judge_engine = _judge_engine()
    model = settings.lm_studio_embedding_model
    embed = lm_studio_embed(settings.lm_studio_url, model)
    now = datetime.now(UTC)
    # embed in committed batches, so a long backfill keeps what it has done
    embedded = 0
    while embedded < embed_limit:
        with session_scope() as session:
            done = embed_pending(
                session, embed, model=model, now=now, limit=min(1000, embed_limit - embedded)
            )
        embedded += done
        if done == 0:
            break
    from news_insight.stories.lock import story_writer

    if judge_engine is None:
        typer.echo(f"embedded={embedded} merge skipped: every judge engine is at its reserve")
        return
    with story_writer() as acquired:
        if not acquired:
            typer.echo(f"embedded={embedded} merge skipped: another story writer is running")
            return
        with session_scope() as session:
            stats = run(
                session,
                embed=embed,
                ask=judge_engine.ask,
                model=model,
                now=now,
                since=now - timedelta(minutes=since_minutes) if since_minutes else None,
                max_judged=max_judged,
                embed_limit=0,
            )
    stats.embedded = embedded
    typer.echo(
        f"embedded={stats.embedded} candidates={stats.candidates} judged={stats.judged} "
        f"merged={stats.merged} guarded={stats.skipped.get('guard', 0)}"
    )


@stories_app.command("eval")
def stories_eval(
    size: Annotated[int, typer.Option(help="Candidate pairs to judge")] = 200,
) -> None:
    """Judge real candidate pairs with Antigravity and report P/R/F1 per MinHash threshold."""
    from news_insight.stories.evaluate import judge, sample_pairs, score

    engine = _judge_engine()
    if engine is None:
        raise _fail("every judge engine is at its reserve")
    with session_scope() as session:
        pairs = sample_pairs(session, now=datetime.now(UTC), size=size)
    labels = judge(engine.ask, pairs)
    same = sum(labels.values())
    typer.echo(f"pairs={len(pairs)} judged={len(labels)} same_event={same}")
    typer.echo("threshold  precision  recall  f1")
    for result in score(pairs, labels):
        cells = [
            f"{value:.2f}" if value is not None else "  - "
            for value in (result.precision, result.recall, result.f1)
        ]
        typer.echo(f"{result.threshold:>9.2f}  {cells[0]:>9}  {cells[1]:>6}  {cells[2]:>4}")


def _briefing_date(on: str | None, now: datetime) -> date:
    return date.fromisoformat(on) if on else now.astimezone(KST).date()


@daily_app.command("freeze")
def daily_freeze(
    on: Annotated[str | None, typer.Option("--date", help="Briefing date YYYY-MM-DD (KST)")] = None,
) -> None:
    """Snapshot today's eligible candidates (idempotent; Celery runs it at 04:40 KST)."""
    from news_insight.briefing.service import freeze

    now = datetime.now(UTC)
    with session_scope() as session:
        snapshot = freeze(session, briefing_date=_briefing_date(on, now), now=now)
        typer.echo(
            f"{snapshot.briefing_date} frozen at {_kst(snapshot.frozen_at)}: "
            f"{len(snapshot.candidate_ids)} candidates"
        )


@daily_app.command("publish")
def daily_publish(
    on: Annotated[str | None, typer.Option("--date", help="Briefing date YYYY-MM-DD (KST)")] = None,
    model: Annotated[str | None, typer.Option(help="Claude model alias")] = None,
    republish: Annotated[
        bool, typer.Option(help="Publish a new version even if the date is already published")
    ] = False,
) -> None:
    """Shortlist the frozen candidates, write the digest, run gates, publish (05:00 KST; launchd
    runs it again at 06:00 and 07:00, which only act while the date has no published briefing)."""
    from news_insight.briefing.service import failing, publish, published_for

    now = datetime.now(UTC)
    day = _briefing_date(on, now)
    with session_scope() as session:
        done = published_for(session, day)
        if done is not None and not republish:
            typer.echo(f"{day} v{done.version} already published; nothing to do")
            return
        briefing = publish(
            session,
            briefing_date=day,
            now=now,
            client=_claude(),
            model=model or get_settings().digest_model,
        )
        line = (
            f"{briefing.briefing_date} v{briefing.version} {briefing.status.value} "
            f"shortlist={len(briefing.shortlist)}"
        )
        blocked = failing(briefing.gates)
    typer.echo(line + (f" failed gates: {', '.join(blocked)}" if blocked else ""))


@periodic_app.command("publish")
def periodic_publish(
    kind: Annotated[
        str | None, typer.Option(help="week or month (default: whatever is due)")
    ] = None,
    key: Annotated[str | None, typer.Option(help="Period key, e.g. 2026-W40 or 2026-09")] = None,
    model: Annotated[str | None, typer.Option(help="Claude model alias")] = None,
    republish: Annotated[bool, typer.Option(help="New version if the input changed")] = False,
) -> None:
    """Weekly and monthly briefings from the daily ones (plan 13 C4). Without --kind/--key it
    writes the last completed week and month that have none yet; the digest job runs it after
    every daily publish, so Monday's 05:00 run produces the week."""
    from news_insight.periodic import service as periodic

    now = datetime.now(UTC)
    with session_scope() as session:
        targets = [(kind, key)] if kind and key else periodic.due(session, now)
        if kind and not key:
            targets = [t for t in periodic.due(session, now) if t[0] == kind]
        for target_kind, target_key in targets:
            row = periodic.generate(
                session,
                kind=target_kind,
                key=target_key,
                now=now,
                client=_claude(),
                model=model or get_settings().digest_model,
                republish=republish,
            )
            if row is None:
                typer.echo(
                    f"{target_kind} {target_key}: fewer than {periodic.MIN_DAYS} daily briefings"
                )
            else:
                state = f"v{row.version} {row.status.value} days={row.days}"
                typer.echo(f"{target_kind} {row.period_key} {state}")
        if not targets:
            typer.echo("nothing due")


@audio_app.command("render")
def audio_render_command(
    on: Annotated[str | None, typer.Option("--date", help="Briefing date YYYY-MM-DD (KST)")] = None,
    force: Annotated[
        bool, typer.Option(help="Render again even if this version has audio")
    ] = False,
) -> None:
    """Speak the published briefing with macOS `say` into MEDIA_DIR (plan 13 A1). Host only:
    the digest job runs it after each publish; a version that already has audio is skipped."""
    from news_insight.audio.render import AudioError, entry_for, render
    from news_insight.audio.script import build_script
    from news_insight.public.briefings import public_briefing, published

    settings = get_settings()
    now = datetime.now(UTC)
    with session_scope() as session:
        briefing = published(session, date.fromisoformat(on) if on else None)
        if briefing is None:
            typer.echo("no published briefing")
            return
        day, version = briefing.briefing_date.isoformat(), briefing.version
        if not force and entry_for(settings.media_dir, day, version):
            typer.echo(f"{day} v{version} already has audio")
            return
        view = public_briefing(session, briefing)
    try:
        entry = render(
            build_script(view),
            media_dir=settings.media_dir,
            briefing_date=day,
            version=version,
            headline=view.headline or "",
            voice=settings.briefing_voice,
            rate=settings.briefing_voice_rate,
            now=now,
        )
    except AudioError as exc:
        typer.echo(f"audio failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{day} v{version} audio {entry.seconds}s {entry.bytes // 1024} KB")


def _account(session: Session, username: str) -> int:
    from news_insight.auth.accounts import find_user

    user = find_user(session, username)
    if user is None:
        raise _fail(f"no user {username!r}")
    return user.id


@users_app.command("create-admin")
def users_create_admin(
    username: str,
    name: Annotated[str, typer.Option(help="Display name")],
    password_stdin: Annotated[
        bool, typer.Option(help="Read the password from the first line of stdin")
    ] = False,
) -> None:
    """Create an active admin account. The password is never taken from argv or the environment."""
    from news_insight.auth.accounts import FormError, create_admin

    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    try:
        with session_scope() as session:
            user = create_admin(
                session, username=username, password=password, name=name, now=datetime.now(UTC)
            )
            typer.echo(f"admin {user.username} created")
    except FormError as error:
        raise _fail(error.message) from None


@users_app.command("list")
def users_list() -> None:
    """List accounts with their role and status."""
    from news_insight.auth.accounts import list_users

    with session_scope() as session:
        for user in list_users(session):
            typer.echo(
                f"{user.username:<32} {user.role.value:<6} {user.status.value:<9} {user.name}"
            )


@users_app.command("approve")
def users_approve(username: str) -> None:
    """Approve a pending (or rejected) sign-up."""
    from news_insight.auth.accounts import ActionError, Client, approve

    try:
        with session_scope() as session:
            approve(
                session, None, _account(session, username), now=datetime.now(UTC), client=Client()
            )
    except ActionError as error:
        raise _fail(str(error)) from None
    typer.echo(f"{username} approved")


@users_app.command("reset-password")
def users_reset_password(username: str) -> None:
    """Print a temporary password; the user must change it at the next login."""
    from news_insight.auth.accounts import ActionError, Client, reset_password

    try:
        with session_scope() as session:
            temporary = reset_password(
                session, None, _account(session, username), now=datetime.now(UTC), client=Client()
            )
    except ActionError as error:
        raise _fail(str(error)) from None
    typer.echo(temporary)


@users_app.command("unlock")
def users_unlock(username: str) -> None:
    """Clear the failed-login lock of an account."""
    from news_insight.auth.accounts import unlock

    with session_scope() as session:
        unlock(session, None, _account(session, username), now=datetime.now(UTC))
    typer.echo(f"{username} unlocked")


@taxonomy_app.command("seed")
def taxonomy_seed(
    backfill: Annotated[bool, typer.Option(help="Rewrite every card's legacy labels too")] = False,
) -> None:
    """Upsert schemes and nodes from the code taxonomy and the technology registry (plan 15)."""
    from news_insight.taxonomy.seed import backfill_labels, seed_taxonomy

    with session_scope() as session:
        result = seed_taxonomy(session, author="cli")
        line = f"created={result.created} updated={result.updated} revision={result.revision_id}"
        if result.skipped:
            line += f" skipped (unknown theme)={','.join(result.skipped[:10])}"
        typer.echo(line)
        if backfill:
            typer.echo(f"legacy labels={backfill_labels(session)}")


@ops_app.command("keys")
def ops_keys() -> None:
    """Check the free API keys from .env against their services; values are never printed."""
    import httpx

    from news_insight.collect import epo_ops
    from news_insight.collect.context import provider_headers
    from news_insight.collect.contracts import CollectorError

    settings = get_settings()
    url = "https://api.openalex.org/rate-limit"
    if not settings.openalex_api_key:
        typer.echo("OpenAlex: OPENALEX_API_KEY is not set")
    else:
        try:
            response = httpx.get(url, headers=provider_headers(url), timeout=30)
            budget = {k: v for k, v in response.headers.items() if k.startswith("x-ratelimit")}
            typer.echo(f"OpenAlex: HTTP {response.status_code} {budget}")
        except httpx.HTTPError as exc:
            typer.echo(f"OpenAlex: unreachable ({type(exc).__name__})")
    try:
        with _fetcher() as fetcher:
            epo_ops._tokens.clear()
            epo_ops._token(fetcher)
        typer.echo("EPO OPS: token issued (key and secret accepted)")
    except CollectorError as exc:
        typer.echo(f"EPO OPS: {exc}")


@ops_app.command("check")
def ops_check(
    apply: Annotated[
        bool, typer.Option(help="Record alert episodes (e-mail only with OPS_ALERT_MAIL)")
    ] = False,
) -> None:
    """Run the health checks (publication SLA, collection, queue, cards) and list findings."""
    from news_insight.jobs.tasks import _host_snapshot, queue_length, slow_requests
    from news_insight.ops.checks import run_checks
    from news_insight.ops.service import notify, sync_alerts

    now = datetime.now(UTC)
    with session_scope() as session:
        findings = run_checks(
            session,
            now=now,
            queue_length=queue_length(),
            slow_requests=slow_requests(now),
            host=_host_snapshot(now),
        )
        if apply:
            notify(get_settings(), sync_alerts(session, findings, now=now), now=now)
    if not findings:
        typer.echo("all checks passed")
    for finding in findings:
        typer.echo(f"[{finding.severity.value}] {finding.key}: {finding.title}")
        if finding.detail:
            typer.echo(f"    {finding.detail}")


@ops_app.command("host-snapshot")
def ops_host_snapshot() -> None:
    """Record macOS memory, swap and the local Qwen state for the console (host only; the card
    job runs it every 10 minutes)."""
    from news_insight.ops.host import collect, save
    from news_insight.scheduling.redis_guards import get_redis

    settings = get_settings()
    snapshot = collect(
        lm_url=settings.lm_studio_url, lm_model=settings.lm_studio_model, now=datetime.now(UTC)
    )
    save(get_redis(), snapshot)
    qwen = snapshot.get("qwen") or {}
    typer.echo(
        f"swap {snapshot.get('swap_used_mb')}/{snapshot.get('swap_total_mb')} MB, "
        f"free {snapshot.get('memory_free_pct')}%, "
        f"qwen {qwen.get('state')} ctx={qwen.get('context')}"
    )


@ops_app.command("logs")
def ops_logs(
    hours: Annotated[float, typer.Option(help="Look back this many hours")] = 24,
    root: Annotated[Path, typer.Option(help="Repository root holding ops/logs")] = Path("../.."),
    write: Annotated[
        Path | None, typer.Option(help="Also write the Markdown report to this file")
    ] = None,
    top: Annotated[int, typer.Option(help="Rows per table")] = 25,
) -> None:
    """Host-side log report: errors grouped by signature, API latency, task failures, card runs."""
    from news_insight.ops.logreport import analyse, collect, render

    until = datetime.now(UTC)
    since = timedelta(hours=hours)
    report = analyse(collect(root.resolve(), since), since=until - since, until=until)
    text = render(report, top=top)
    if write is not None:
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text(text, encoding="utf-8")
    typer.echo(text)


@ops_app.command("audit")
def ops_audit(
    write: Annotated[Path | None, typer.Option(help="Also write the Markdown report here")] = None,
    containers: Annotated[bool, typer.Option(help="Include docker stats (host only)")] = True,
) -> None:
    """Read-only audit of the whole flow: collection, duplicates, cards, classification, stories,
    database and containers, with findings ranked by severity."""
    from news_insight.ops.audit import render, run_audit

    with session_scope() as session:
        text = render(run_audit(session, with_containers=containers))
    if write is not None:
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text(text, encoding="utf-8")
    typer.echo(text)


@tech_app.command("seed")
def technologies_seed() -> None:
    """Upsert catalog/technologies.yaml, then recompute card keys and labels."""
    from news_insight.technologies.catalog import load_technologies
    from news_insight.technologies.service import recompute_all, refresh_labels, seed_registry

    with session_scope() as session:
        result = seed_registry(session, load_technologies())
        changed = recompute_all(session)
        labels = refresh_labels(session, now=datetime.now(UTC))
    typer.echo(
        f"created={result.created} updated={result.updated} aliases_added={result.aliases_added} "
        f"cards_rekeyed={changed} labels={labels}"
    )


@tech_app.command("recompute")
def technologies_recompute() -> None:
    """Re-derive every card's technology keys and the display labels."""
    from news_insight.technologies.service import recompute_all, refresh_labels

    with session_scope() as session:
        changed = recompute_all(session)
        labels = refresh_labels(session, now=datetime.now(UTC))
    typer.echo(f"cards_rekeyed={changed} labels={labels}")


@tech_app.command("candidates")
def technologies_candidates(
    days: Annotated[int, typer.Option(help="Window in days")] = 30,
    min_count: Annotated[int, typer.Option(help="Minimum DX-relevant cards")] = 10,
) -> None:
    """Frequent keyword keys the registry does not know yet."""
    from news_insight.technologies.service import candidates, labels_for

    with session_scope() as session:
        rows = candidates(session, now=datetime.now(UTC), days=days, min_count=min_count)
        labels = labels_for(session, [key for key, _ in rows])
    for key, count in rows:
        typer.echo(f"{count:5d}  {labels[key]}  ({key})")


@companies_app.command("seed")
def companies_seed() -> None:
    """Upsert catalog/companies.yaml, then recompute card company keys."""
    from news_insight.companies.catalog import load_companies
    from news_insight.companies.service import recompute_all, seed_registry

    with session_scope() as session:
        result = seed_registry(session, load_companies())
        changed = recompute_all(session)
    typer.echo(
        f"created={result.created} updated={result.updated} aliases_added={result.aliases_added} "
        f"cards_rekeyed={changed}"
    )


@companies_app.command("recompute")
def companies_recompute() -> None:
    """Re-derive every card's company keys after registry edits."""
    from news_insight.companies.service import recompute_all

    with session_scope() as session:
        changed = recompute_all(session)
    typer.echo(f"cards_rekeyed={changed}")


@companies_app.command("backfill")
def companies_backfill(
    days: Annotated[int, typer.Option(help="Cards first seen in the last N days")] = 90,
    dry_run: Annotated[bool, typer.Option(help="Count only")] = False,
) -> None:
    """Queue recent DX-relevant cards without an engine company list for reclassification."""
    from news_insight.companies.service import mark_backfill

    with session_scope() as session:
        count = mark_backfill(session, now=datetime.now(UTC), days=days, apply=not dry_run)
    typer.echo(f"{'would queue' if dry_run else 'queued'} {count} cards")


@companies_app.command("candidates")
def companies_candidates(
    days: Annotated[int, typer.Option(help="Window in days")] = 30,
    min_count: Annotated[int, typer.Option(help="Minimum DX-relevant cards")] = 3,
) -> None:
    """Company names on recent cards that the registry does not know (new = no earlier report)."""
    from news_insight.companies.service import candidates

    with session_scope() as session:
        rows = candidates(session, now=datetime.now(UTC), days=days, min_count=min_count)
    for row in rows:
        new = "new" if row.earlier == 0 else f"earlier={row.earlier}"
        typer.echo(f"{row.cards:5d}  sources={row.sources:3d}  {new:12s} {row.name}  ({row.key})")


@taxonomy_app.command("provisional")
def taxonomy_provisional() -> None:
    """Map cards from the previous tree to the current one until the LLM reclassifies them."""
    from news_insight.taxonomy.provisional import apply_provisional

    with session_scope() as session:
        result = apply_provisional(session)
    typer.echo(
        f"mapped={result.mapped} from_keywords={result.from_keywords} "
        f"without_theme={result.without_theme}"
    )


@stories_app.command("refs-backfill")
def stories_refs_backfill(
    days: Annotated[int, typer.Option(help="Items first seen in the last N days")] = 30,
) -> None:
    """Re-extract cross-track identifiers (new kinds: CVE, 3GPP, patent, Hugging Face)."""
    from sqlalchemy.dialects.postgresql import insert

    from news_insight.content.models import Item
    from news_insight.stories.models import ItemRef
    from news_insight.stories.refs import extract_refs

    since = datetime.now(UTC) - timedelta(days=days)
    with session_scope() as session:
        before = session.scalar(select(func.count()).select_from(ItemRef)) or 0
        rows = session.execute(
            select(Item.id, Item.url, Item.title, Item.summary).where(Item.first_seen_at >= since)
        ).all()
        for item_id, url, title, summary in rows:
            refs = extract_refs(url, title, summary)
            if refs:
                session.execute(
                    insert(ItemRef)
                    .values(
                        [
                            {"item_id": item_id, "kind": k, "value": v[:300], "meta": {}}
                            for k, v in refs
                        ]
                    )
                    .on_conflict_do_nothing()
                )
        added = (session.scalar(select(func.count()).select_from(ItemRef)) or 0) - before
    typer.echo(f"items={len(rows)} refs_added={added}")


def main() -> None:
    """Entry point: a failing command leaves one JSON error line (with the trace) in the job log."""
    import logging
    import sys

    try:
        app()
    except SystemExit:
        raise
    except Exception:
        logging.getLogger("news_insight.cli").exception(
            "command failed", extra={"argv": sys.argv[1:]}
        )
        raise SystemExit(1) from None
