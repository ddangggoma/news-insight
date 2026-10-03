"""Operator CLI: `news-insight sources seed|validate|promote|report`."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from news_insight.config import get_settings
from news_insight.db import session_scope
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.catalog import DEFAULT_CATALOG_PATH, load_catalog, seed_catalog
from news_insight.sources.enums import STAGE_ORDER, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import LadderError
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
    run_check,
    stage_counts,
)

app = typer.Typer(help="Daily IT Intelligence operations CLI", no_args_is_help=True)
sources_app = typer.Typer(help="Source registry and V0-V6 validation ladder", no_args_is_help=True)
app.add_typer(sources_app, name="sources")

CLIMBABLE = (ValidationStage.V0, ValidationStage.V1, ValidationStage.V2, ValidationStage.V3)


def _fetcher() -> SafeFetcher:
    return SafeFetcher.from_settings(get_settings())


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
