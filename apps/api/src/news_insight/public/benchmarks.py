"""AI model leaderboards for readers (plan 18): each site's latest snapshot as the site stores it,
with a rank per board and the move against the snapshot before. The all-sites view is a summary
(top ten per board); one site's full rows come from its own request.

The rank follows one representative metric per site (higher is better for all four):
DeepSWE `pass_at_1`, LiveBench the site's weighted mean of its distinct category metrics (a
derived `overall` row: the table has no overall column and the site weighs Long Agentic, Coding
and Design above the rest; a model covering under 75% of the board's categories keeps the row
unranked), LMArena `rating` (the agent board: `score`), Artificial
Analysis its intelligence index. A model is one entry per board (its id when linked, else its
normalized name) and ranks by its best row, so only that row carries a rank."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import ModuleType
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
SUMMARY_ROWS = 10  # ranked rows per board in the all-sites summary
MIN_COVERAGE = 0.75  # share of a LiveBench board's categories a model needs to be ranked
OVERALL = "overall"
_MODEL_INFO = ("display_name", "organization", "open_weights")  # LiveBench's model metadata
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


class UnknownSite(LookupError):
    """No leaderboard site of that name."""


@dataclass
class _Score:
    """What ranking needs of one stored row, read without its extra or the snapshot's raw."""

    id: int  # the row it stands for (a derived row: the first row of its model)
    board: str
    key: str
    model: str
    metric: str
    value: float
    derived: bool = False
    categories: tuple[str, ...] = ()
    coverage: float = 1.0
    eligible: bool = True


def _key(model_id: int | None, raw: str) -> str:
    return f"id:{model_id}" if model_id is not None else f"name:{normalize(raw) or raw}"


def _scores(session: Session, site: str, snapshot_id: int) -> list[_Score]:
    found = session.execute(
        select(
            BenchmarkScore.id,
            BenchmarkScore.board,
            BenchmarkScore.model_id,
            BenchmarkScore.model_raw,
            BenchmarkScore.metric,
            BenchmarkScore.value,
        )
        .where(BenchmarkScore.snapshot_id == snapshot_id)
        .order_by(BenchmarkScore.board, BenchmarkScore.id)
    )
    scores = [
        _Score(row_id, board, _key(model_id, raw), raw, metric, value)
        for row_id, board, model_id, raw, metric, value in found
    ]
    if site == livebench.SITE:
        scores += _livebench_overall(scores, _livebench_weights(session, snapshot_id))
    return scores


def _livebench_weights(session: Session, snapshot_id: int) -> dict[str, float]:
    """The site's category weights ({"coding": 1.5, ...}) from the snapshot's categories.json:
    `_overall_weights` names categories by label ("Long Agentic"), the same file maps a label to
    its metric names. Only that one key of the raw JSON is read; a missing or odd entry is a
    weight of 1."""
    categories = session.scalar(
        select(BenchmarkSnapshot.raw["categories"]).where(BenchmarkSnapshot.id == snapshot_id)
    )
    weights = categories.get("_overall_weights") if isinstance(categories, dict) else None
    if not isinstance(categories, dict) or not isinstance(weights, dict):
        return {}
    found: dict[str, float] = {}
    for label, weight in weights.items():
        columns = categories.get(label)
        if isinstance(weight, bool) or not isinstance(weight, int | float):
            continue
        if not math.isfinite(weight) or weight <= 0 or not isinstance(columns, list):
            continue
        found.update({c.casefold(): float(weight) for c in columns if isinstance(c, str)})
    return found


def _livebench_overall(scores: list[_Score], weights: dict[str, float]) -> list[_Score]:
    """One derived row per model: the site's overall, the weighted mean over the distinct
    categories the model has (unlisted categories weigh 1; a category stored under several
    spellings of the model counts once; the cost is not a category). Only a model covering
    MIN_COVERAGE of the board's categories may rank."""
    board_categories: dict[str, set[str]] = {}
    models: dict[tuple[str, str], dict[str, list[float]]] = {}
    first: dict[tuple[str, str], _Score] = {}
    for score in scores:
        if score.metric == livebench.COST_METRIC:
            continue
        category = score.metric.casefold()
        board_categories.setdefault(score.board, set()).add(category)
        models.setdefault((score.board, score.key), {}).setdefault(category, []).append(score.value)
        first.setdefault((score.board, score.key), score)
    derived = []
    for (board, key), by_category in models.items():
        weighted = [
            (weights.get(category, 1.0), sum(values) / len(values))
            for category, values in by_category.items()
        ]
        total = sum(weight for weight, _ in weighted)
        coverage = len(by_category) / len(board_categories[board])
        source = first[(board, key)]
        derived.append(
            _Score(
                source.id,
                board,
                key,
                source.model,
                OVERALL,
                sum(weight * mean for weight, mean in weighted) / total,
                derived=True,
                categories=tuple(sorted(by_category)),
                coverage=coverage,
                eligible=coverage >= MIN_COVERAGE,
            )
        )
    return derived


def _ranking(site: str, scores: list[_Score]) -> dict[str, list[_Score]]:
    """Per board, each eligible model's best row on the representative metric, best first."""
    best: dict[tuple[str, str], _Score] = {}
    for score in scores:
        if score.metric != representative_metric(site, score.board) or not score.eligible:
            continue
        slot = (score.board, score.key)
        if slot not in best or score.value > best[slot].value:
            best[slot] = score
    boards: dict[str, list[_Score]] = {}
    for (board, _), score in best.items():
        boards.setdefault(board, []).append(score)
    for ranked in boards.values():
        ranked.sort(key=lambda sc: (-sc.value, sc.model.casefold()))
    return boards


def _places(ranking: dict[str, list[_Score]]) -> dict[str, dict[str, int]]:
    return {
        board: {score.key: place for place, score in enumerate(scores, start=1)}
        for board, scores in ranking.items()
    }


def _rows(session: Session, ids: list[int] | None, snapshot_id: int) -> dict[int, BenchmarkRowOut]:
    """Full rows (with extra and the registry's org) of a snapshot, or of the given ids."""
    query = (
        select(BenchmarkScore, AiModel.org)
        .outerjoin(AiModel, AiModel.id == BenchmarkScore.model_id)
        .where(BenchmarkScore.snapshot_id == snapshot_id)
    )
    if ids is not None:
        query = query.where(BenchmarkScore.id.in_(ids))
    return {
        score.id: BenchmarkRowOut(
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
        )
        for score, registry_org in session.execute(query)
    }


def _derived_row(score: _Score, source: BenchmarkRowOut) -> BenchmarkRowOut:
    # who the model is travels with it, as the table rows carry it
    named = {k: v for k, v in source.extra.items() if k in _MODEL_INFO}
    return source.model_copy(
        update={
            "config": None,
            "metric": OVERALL,
            "value": score.value,
            "ci_low": None,
            "ci_high": None,
            "extra": {
                **named,
                "derived": True,
                "categories": list(score.categories),
                "coverage": round(score.coverage, 3),
            },
        }
    )


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


def _moved(now_rank: int, was: int | None) -> tuple[Change, int]:
    if was is None:
        return "new", 0
    if now_rank < was:
        return "up", was - now_rank
    if now_rank > was:
        return "down", now_rank - was
    return "same", 0


def _site_out(
    session: Session,
    module: ModuleType,
    snapshots: list[BenchmarkSnapshot],
    *,
    now: datetime,
    full: bool,
) -> BenchmarkSiteOut:
    site: str = module.SITE
    latest = snapshots[0]
    scores = _scores(session, site, latest.id)
    ranking = _ranking(site, scores)
    before = (
        _places(_ranking(site, _scores(session, site, snapshots[1].id)))
        if len(snapshots) > 1
        else {}
    )
    boards = list(dict.fromkeys(score.board for score in scores))
    order = {board: index for index, board in enumerate(boards)}
    shown = {board: ranked if full else ranked[:SUMMARY_ROWS] for board, ranked in ranking.items()}
    rows = _rows(
        session, None if full else [s.id for ranked in shown.values() for s in ranked], latest.id
    )
    out_rows: list[BenchmarkRowOut] = []
    ranked_stored: set[int] = set()
    for board, ranked in shown.items():
        for place, score in enumerate(ranked, start=1):
            row = _derived_row(score, rows[score.id]) if score.derived else rows[score.id]
            row.rank = place
            if board in before:
                row.change, row.change_by = _moved(place, before[board].get(score.key))
            out_rows.append(row)
            if not score.derived:
                ranked_stored.add(score.id)
    if full:
        out_rows += [row for row_id, row in rows.items() if row_id not in ranked_stored]
        # a model too sparsely measured to rank keeps its derived row, unranked
        out_rows += [
            _derived_row(score, rows[score.id])
            for score in scores
            if score.derived and not score.eligible
        ]
    out_rows.sort(key=lambda r: (order[r.board], r.rank is None, r.rank or 0, r.model, r.metric))
    return BenchmarkSiteOut(
        site=site,
        title=module.TITLE,
        source_url=module.SOURCE_URL,
        license=module.LICENSE,
        attribution=module.ATTRIBUTION,
        release=latest.release,
        fetched_at=latest.fetched_at,
        stale=now - latest.fetched_at > STALE_AFTER,
        boards=boards,
        rows=out_rows,
    )


def benchmarks_view(
    session: Session, *, now: datetime, site: str | None = None
) -> list[BenchmarkSiteOut]:
    """Without `site`: every collected site's summary (its top SUMMARY_ROWS ranked rows per
    board). With `site`: that site's full rows, as a one-element list (empty when it has never
    been collected); an unknown name raises UnknownSite. Always the snapshot seen last."""
    if site is not None and site not in {m.SITE for m in SITES}:
        raise UnknownSite(site)
    out: list[BenchmarkSiteOut] = []
    for module in SITES:
        if site is not None and site != module.SITE:
            continue
        snapshots = _latest_two(session, module.SITE)
        if snapshots:
            out.append(_site_out(session, module, snapshots, now=now, full=site is not None))
    return out


def benchmark_changes(session: Session, *, now: datetime) -> dict[str, Any]:
    """What moved in the representative top 20 of each site and board when the latest snapshot
    replaced the one before (only while that earlier snapshot was current within two days, so
    the same move is not told again every day): `changes` for models in the top 20 both times
    whose rank differs, `new_models` for models that entered the top 20."""
    changes: list[dict[str, Any]] = []
    new_models: list[dict[str, Any]] = []
    for module in SITES:
        site: str = module.SITE
        snapshots = _latest_two(session, site)
        if len(snapshots) < 2 or now - snapshots[1].fetched_at > CHANGE_WINDOW:
            continue
        after = _ranking(site, _scores(session, site, snapshots[0].id))
        before = _places(_ranking(site, _scores(session, site, snapshots[1].id)))
        for board, ranked in after.items():
            if board not in before:
                continue
            for place, score in enumerate(ranked[:TOP], start=1):
                was = before[board].get(score.key)
                base = {"site": module.TITLE, "board": board, "model": score.model}
                if was is None or was > TOP:
                    new_models.append({**base, "rank": place, "previous_rank": was})
                elif was != place:
                    changes.append({**base, "from": was, "to": place})
    return {"changes": changes, "new_models": new_models}


def top_holders(
    session: Session, *, now: datetime, days: int = 7, top: int = 5, min_days: int = 3
) -> list[dict[str, Any]]:
    """Models that held a place in a board's top `top` through the last `days` days: in every
    snapshot of a site fetched in that span, and in the one current when it began (a site's
    snapshot is stored only when its bytes change, so the last one before the span still held
    on its first day). The span the snapshots cover must reach `min_days` calendar days; a
    stale site is skipped. One row per site, board and model: its current and best rank and
    how many days it held on."""
    start = now - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for module in SITES:
        site: str = module.SITE
        snapshots = list(
            session.scalars(
                select(BenchmarkSnapshot)
                .options(defer(BenchmarkSnapshot.raw))
                .where(
                    BenchmarkSnapshot.site == site,
                    BenchmarkSnapshot.fetched_at >= start,
                    BenchmarkSnapshot.fetched_at <= now,
                )
                .order_by(BenchmarkSnapshot.fetched_at, BenchmarkSnapshot.id)
            )
        )
        before = session.scalars(
            select(BenchmarkSnapshot)
            .options(defer(BenchmarkSnapshot.raw))
            .where(BenchmarkSnapshot.site == site, BenchmarkSnapshot.fetched_at < start)
            .order_by(BenchmarkSnapshot.fetched_at.desc(), BenchmarkSnapshot.id.desc())
            .limit(1)
        ).first()
        covering = ([before] if before is not None else []) + snapshots
        if not covering or now - covering[-1].fetched_at > STALE_AFTER:
            continue
        since = max(covering[0].fetched_at, start)
        held_days = (now.date() - since.date()).days + 1
        if held_days < min_days:
            continue
        places = [
            {
                board: {s.key: (place, s.model) for place, s in enumerate(ranked[:top], start=1)}
                for board, ranked in _ranking(site, _scores(session, site, snap.id)).items()
            }
            for snap in covering
        ]
        for board, latest in places[-1].items():
            for key, (rank, model) in latest.items():
                ranks = [found[board][key][0] for found in places if key in found.get(board, {})]
                if len(ranks) != len(places):
                    continue
                out.append(
                    {
                        "site": module.TITLE,
                        "board": board,
                        "model": model,
                        "rank": rank,
                        "best_rank": min(ranks),
                        "days": min(held_days, days),
                    }
                )
    return out
