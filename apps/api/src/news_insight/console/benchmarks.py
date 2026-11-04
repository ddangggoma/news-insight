"""Console view and edit for model names the leaderboards use that no AiModel owns yet.

A site's name stays unmatched until someone links it here: the alias is kept as written (matched
exactly from then on), the model is created when it does not exist, and every score row of the
same spelling (exactly, or once normalized) gets its model_id."""

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import distinct, select, update
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import (
    AiModel,
    AiModelAlias,
    BenchmarkScore,
    BenchmarkSnapshot,
)
from news_insight.benchmarks.names import normalize


class InvalidName(ValueError):
    """The model name is empty once normalized."""


class AliasTaken(ValueError):
    """The alias already belongs to another model."""


class UnmatchedOut(BaseModel):
    model_raw: str
    org: str | None
    sites: list[str]
    last_seen: datetime


class AliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=200)  # ai_model_aliases.alias
    model_name: str = Field(min_length=1, max_length=120)  # ai_models.name
    org: str | None = Field(default=None, max_length=80)  # ai_models.org


class AliasOut(BaseModel):
    model_id: int
    model: str
    linked: int  # score rows that got the model


def unmatched(session: Session) -> list[UnmatchedOut]:
    """Names without a model in each site's latest snapshot (older ones are history)."""
    latest: dict[str, tuple[int, datetime]] = {}
    for snapshot_id, site, fetched_at in session.execute(
        select(BenchmarkSnapshot.id, BenchmarkSnapshot.site, BenchmarkSnapshot.fetched_at).order_by(
            BenchmarkSnapshot.site, BenchmarkSnapshot.fetched_at.desc(), BenchmarkSnapshot.id.desc()
        )
    ):
        latest.setdefault(site, (snapshot_id, fetched_at))
    seen = {snapshot_id: fetched_at for snapshot_id, fetched_at in latest.values()}
    found = session.execute(
        select(
            distinct(BenchmarkScore.model_raw),
            BenchmarkScore.org,
            BenchmarkScore.site,
            BenchmarkScore.snapshot_id,
        ).where(BenchmarkScore.snapshot_id.in_(seen), BenchmarkScore.model_id.is_(None))
    )
    orgs: dict[str, set[str]] = {}
    sites: dict[str, set[str]] = {}
    last: dict[str, datetime] = {}
    for model_raw, org, site, snapshot_id in found:
        orgs.setdefault(model_raw, set())
        if org:
            orgs[model_raw].add(org)
        sites.setdefault(model_raw, set()).add(site)
        last[model_raw] = max(seen[snapshot_id], last.get(model_raw, seen[snapshot_id]))
    return [
        UnmatchedOut(
            model_raw=model_raw,
            org=min(orgs[model_raw]) if orgs[model_raw] else None,
            sites=sorted(sites[model_raw]),
            last_seen=last[model_raw],
        )
        for model_raw in sorted(sites, key=str.casefold)
    ]


def link_alias(session: Session, body: AliasIn) -> AliasOut:
    """Create the model and alias when missing and fill model_id on every matching score."""
    alias = body.alias.strip()
    name = normalize(body.model_name)
    if not alias or not name:
        raise InvalidName("alias and model name must not be empty")
    model = session.scalar(select(AiModel).where(AiModel.name == name))
    taken = session.scalar(select(AiModelAlias).where(AiModelAlias.alias == alias))
    if taken is not None and (model is None or taken.model_id != model.id):
        raise AliasTaken(f"'{alias}' is already linked to another model")
    if model is None:
        model = AiModel(name=name, org=body.org)
        session.add(model)
        session.flush()
    elif model.org is None and body.org:
        model.org = body.org
    if taken is None:
        session.add(AiModelAlias(alias=alias, model_id=model.id))
    slug = normalize(alias)
    names = session.scalars(
        select(distinct(BenchmarkScore.model_raw)).where(BenchmarkScore.model_id.is_(None))
    )
    matching = [n for n in names if n == alias or (slug and normalize(n) == slug)]
    linked = 0
    if matching:
        result = session.execute(
            update(BenchmarkScore)
            .where(BenchmarkScore.model_raw.in_(matching), BenchmarkScore.model_id.is_(None))
            .values(model_id=model.id)
        )
        linked = int(getattr(result, "rowcount", 0) or 0)
    session.flush()
    return AliasOut(model_id=model.id, model=model.name, linked=linked)
