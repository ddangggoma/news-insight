"""AI model leaderboards for readers (plan 18): each site's latest snapshot as the site stores it,
with a rank per board and the move against the snapshot before.

The rank follows one representative metric per site (higher is better for all four):
DeepSWE `pass_at_1`, LiveBench the mean of its category metrics (a derived `overall` row: the
site's table has no overall column), LMArena `rating` (the agent board: `score`), Artificial
Analysis its intelligence index. A model is one entry per board (its id when linked, else its
normalized name) and ranks by its best row, so only that row carries a rank."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from news_insight.benchmarks.models import AiModel, BenchmarkScore, BenchmarkSnapshot
from news_insight.benchmarks.names import normalize
from news_insight.benchmarks.sources import artificial_analysis, deepswe, livebench, lmarena

Change = Literal["new", "up", "down", "same"]

STALE_AFTER = timedelta(hours=48)
CHANGE_WINDOW = STALE_AFTER  # the earlier snapshot was still current this recently
TOP = 20  # the ranks whose moves the spotlight writer is told about
OVERALL = "overall"
INTELLIGENCE_INDEX = "artificial_analysis_intelligence_index"
AGENT_BOARD = "agent"

SITES = (deepswe, livebench, lmarena, artificial_analysis)


class BenchmarkRowOut(BaseModel):
    board: str
    model: str  # the site's own spelling
    model_id: int | None
    org: str | None
    config: str | None
    metric: str
    value: float
    ci_low: float | None
    ci_high: float | None
    extra: dict[str, Any]
    rank: int | None  # only the best row of a model, on the site's representative metric
    change: Change | None  # against the previous snapshot; None where there is nothing to compare
    change_by: int  # places moved; 0 for same and new


class BenchmarkSiteOut(BaseModel):
    site: str
    title: str
    source_url: str
    license: str
    attribution: str
    release: str
    fetched_at: datetime  # last seen: an unchanged fetch touches it
    stale: bool
    boards: list[str]
    rows: list[BenchmarkRowOut]


def representative_metric(site: str, board: str) -> str:
    if site == deepswe.SITE:
        return "pass_at_1"
    if site == livebench.SITE:
        return OVERALL
    if site == lmarena.SITE:
        return "score" if board == AGENT_BOARD else "rating"
    return INTELLIGENCE_INDEX


@dataclass(frozen=True)
class _Entry:
    key: str
    row: BenchmarkRowOut


def _key(model_id: int | None, raw: str) -> str:
    return f"id:{model_id}" if model_id is not None else f"name:{normalize(raw) or raw}"


def _entries(session: Session, site: str, snapshot_id: int) -> list[_Entry]:
    found = session.execute(
        select(BenchmarkScore, AiModel.org)
        .outerjoin(AiModel, AiModel.id == BenchmarkScore.model_id)
        .where(BenchmarkScore.snapshot_id == snapshot_id)
        .order_by(BenchmarkScore.board, BenchmarkScore.id)
    )
    entries = [
        _Entry(
            _key(score.model_id, score.model_raw),
            BenchmarkRowOut(
                board=score.board,
                model=score.model_raw,
                model_id=score.model_id,
                org=score.org or registry_org,
                config=score.config,
                metric=score.metric,
                value=score.value,
                ci_low=score.ci_low,
                ci_high=score.ci_high,
                extra=score.extra or {},
                rank=None,
                change=None,
                change_by=0,
            ),
        )
        for score, registry_org in found
    ]
    if site == livebench.SITE:
        entries += _livebench_overall(entries)
    return entries


def _livebench_overall(entries: list[_Entry]) -> list[_Entry]:
    """One derived row per model: the arithmetic mean of its category metrics (not the cost)."""
    groups: dict[tuple[str, str], list[BenchmarkRowOut]] = {}
    for entry in entries:
        if entry.row.metric != livebench.COST_METRIC:
            groups.setdefault((entry.row.board, entry.key), []).append(entry.row)
    derived = []
    for (board, key), rows in groups.items():
        first = rows[0]
        derived.append(
            _Entry(
                key,
                first.model_copy(
                    update={
                        "board": board,
                        "config": None,
                        "metric": OVERALL,
                        "value": sum(r.value for r in rows) / len(rows),
                        "ci_low": None,
                        "ci_high": None,
                        "extra": {
                            "derived": True,
                            "categories": sorted({r.metric for r in rows}),
                        },
                    }
                ),
            )
        )
    return derived


def _ranking(site: str, entries: list[_Entry]) -> dict[str, list[_Entry]]:
    """Per board, each model's best row on the representative metric, best first."""
    best: dict[tuple[str, str], _Entry] = {}
    for entry in entries:
        row = entry.row
        if row.metric != representative_metric(site, row.board):
            continue
        slot = (row.board, entry.key)
        if slot not in best or row.value > best[slot].row.value:
            best[slot] = entry
    boards: dict[str, list[_Entry]] = {}
    for (board, _), entry in best.items():
        boards.setdefault(board, []).append(entry)
    for ranked in boards.values():
        ranked.sort(key=lambda e: (-e.row.value, e.row.model.casefold()))
    return boards


def _latest_two(session: Session, site: str) -> list[BenchmarkSnapshot]:
    return list(
        session.scalars(
            select(BenchmarkSnapshot)
            .options(defer(BenchmarkSnapshot.raw))
            .where(BenchmarkSnapshot.site == site)
            .order_by(BenchmarkSnapshot.fetched_at.desc(), BenchmarkSnapshot.id.desc())
            .limit(2)
        )
    )


def _places(ranking: dict[str, list[_Entry]]) -> dict[str, dict[str, int]]:
    return {
        board: {entry.key: place for place, entry in enumerate(entries, start=1)}
        for board, entries in ranking.items()
    }


def _moved(now_rank: int, was: int | None) -> tuple[Change, int]:
    if was is None:
        return "new", 0
    if now_rank < was:
        return "up", was - now_rank
    if now_rank > was:
        return "down", now_rank - was
    return "same", 0


def benchmarks_view(session: Session, *, now: datetime) -> list[BenchmarkSiteOut]:
    """Every collected site's latest snapshot (the one seen last), in the sites' fixed order."""
    out: list[BenchmarkSiteOut] = []
    for module in SITES:
        snapshots = _latest_two(session, module.SITE)
        if not snapshots:
            continue
        latest = snapshots[0]
        entries = _entries(session, module.SITE, latest.id)
        ranking = _ranking(module.SITE, entries)
        before = (
            _places(_ranking(module.SITE, _entries(session, module.SITE, snapshots[1].id)))
            if len(snapshots) > 1
            else {}
        )
        for board, ranked in ranking.items():
            for place, entry in enumerate(ranked, start=1):
                entry.row.rank = place
                if board in before:
                    entry.row.change, entry.row.change_by = _moved(
                        place, before[board].get(entry.key)
                    )
        boards = list(dict.fromkeys(e.row.board for e in entries))
        order = {board: index for index, board in enumerate(boards)}
        rows = sorted(
            (e.row for e in entries),
            key=lambda r: (order[r.board], r.rank is None, r.rank or 0, r.model, r.metric),
        )
        out.append(
            BenchmarkSiteOut(
                site=module.SITE,
                title=module.TITLE,
                source_url=module.SOURCE_URL,
                license=module.LICENSE,
                attribution=module.ATTRIBUTION,
                release=latest.release,
                fetched_at=latest.fetched_at,
                stale=now - latest.fetched_at > STALE_AFTER,
                boards=boards,
                rows=rows,
            )
        )
    return out


def benchmark_changes(session: Session, *, now: datetime) -> dict[str, Any]:
    """What moved in the representative top 20 of each site and board when the latest snapshot
    replaced the one before (only while that earlier snapshot was current within two days, so
    the same move is not told again every day): `changes` for models in the top 20 both times
    whose rank differs, `new_models` for models that entered the top 20."""
    changes: list[dict[str, Any]] = []
    new_models: list[dict[str, Any]] = []
    for module in SITES:
        snapshots = _latest_two(session, module.SITE)
        if len(snapshots) < 2 or now - snapshots[1].fetched_at > CHANGE_WINDOW:
            continue
        after = _ranking(module.SITE, _entries(session, module.SITE, snapshots[0].id))
        before = _places(_ranking(module.SITE, _entries(session, module.SITE, snapshots[1].id)))
        for board, ranked in after.items():
            if board not in before:
                continue
            for place, entry in enumerate(ranked[:TOP], start=1):
                was = before[board].get(entry.key)
                base = {"site": module.TITLE, "board": board, "model": entry.row.model}
                if was is None or was > TOP:
                    new_models.append({**base, "rank": place, "previous_rank": was})
                elif was != place:
                    changes.append({**base, "from": was, "to": place})
    return {"changes": changes, "new_models": new_models}
