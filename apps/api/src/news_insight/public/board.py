"""Opportunity and threat board (plan 16 #10): for each technology area over the last days,
how many cards read as opportunity, risk or watch with the strongest evidence for each, the
daily briefings' roadmap claims placed on a 1-, 3- or 5-year horizon, and — for a chosen
role — how that persona read the area. Claims land on the area most of their cited cards
belong to."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingStatus
from news_insight.cards.models import ItemCard
from news_insight.content.models import Item
from news_insight.public.filters import ReaderFilters, joined
from news_insight.public.periods import KST
from news_insight.strategy.models import StrategyRun
from news_insight.strategy.personas import PERSONAS
from news_insight.taxonomy.models import CardLabel, TaxNode, TaxScheme

IMPACTS = ("opportunity", "risk", "watch")
HORIZONS = ("1y", "3y", "5y")
ROWS = 25


class Evidence(BaseModel):
    item_id: int
    title: str
    first_seen_at: datetime


class BoardClaim(BaseModel):
    text: str
    kind: str  # roadmap | opportunity | risk
    horizon: str | None
    briefing_date: str
    item_ids: list[int]


class PersonaRead(BaseModel):
    stances: dict[str, int]  # opportunity / risk / watch -> days the persona read it so
    headlines: list[str]


class BoardRow(BaseModel):
    key: str
    label: str
    field_label: str
    counts: dict[str, int]
    evidence: dict[str, list[Evidence]]
    horizons: dict[str, list[BoardClaim]]
    claims: list[BoardClaim]  # briefing opportunities and risks without a horizon
    persona: PersonaRead | None = None


class PersonaOption(BaseModel):
    key: str
    name: str
    group: str


class BoardView(BaseModel):
    days: int
    persona: str | None
    personas: list[PersonaOption]
    rows: list[BoardRow]


def _areas_of(session: Session, item_ids: set[int]) -> dict[int, int]:
    """Each item's main second-level technology area (its first label by node depth)."""
    if not item_ids:
        return {}
    area = func.coalesce(TaxNode.path[2], TaxNode.id)
    out: dict[int, int] = {}
    for item_id, node in session.execute(
        select(CardLabel.item_id, area)
        .join(TaxNode, TaxNode.id == CardLabel.node_id)
        .join(TaxScheme, TaxScheme.id == TaxNode.scheme_id)
        .where(TaxScheme.key == "technology", TaxNode.depth >= 2, CardLabel.item_id.in_(item_ids))
        .order_by(CardLabel.item_id, TaxNode.depth)
    ).tuples():
        out.setdefault(item_id, node)
    return out


def _claim_area(item_ids: list[int], areas: dict[int, int]) -> int | None:
    found = Counter(areas[i] for i in item_ids if i in areas)
    return found.most_common(1)[0][0] if found else None


def board_view(
    session: Session, *, now: datetime, days: int = 30, persona: str | None = None
) -> BoardView:
    since = now - timedelta(days=days)
    area = func.coalesce(TaxNode.path[2], TaxNode.id)
    rows = session.execute(
        joined(
            select(
                area.label("area"),
                Item.id,
                func.coalesce(ItemCard.title_ko, Item.title).label("title"),
                Item.first_seen_at,
                ItemCard.impact,
                ItemCard.relevance,
            )
        )
        .join(CardLabel, CardLabel.item_id == Item.id)
        .join(TaxNode, TaxNode.id == CardLabel.node_id)
        .join(TaxScheme, TaxScheme.id == TaxNode.scheme_id)
        .where(
            *ReaderFilters().conditions(),
            TaxScheme.key == "technology",
            TaxNode.depth >= 2,
            Item.first_seen_at >= since,
            ItemCard.impact.in_(IMPACTS),
        )
        .distinct()
    ).all()
    counts: dict[int, Counter[str]] = defaultdict(Counter)
    best: dict[int, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for card in rows:
        counts[card.area][card.impact] += 1
        best[card.area][card.impact].append(card)

    # the published briefings of the window: their strategy claims and persona readings
    latest = (
        select(Briefing.briefing_date, func.max(Briefing.version).label("version"))
        .where(
            Briefing.status == BriefingStatus.PUBLISHED,
            Briefing.briefing_date >= since.astimezone(KST).date(),
        )
        .group_by(Briefing.briefing_date)
        .subquery()
    )
    runs = (
        session.execute(
            select(Briefing.briefing_date, StrategyRun.report, StrategyRun.personas)
            .join(
                latest,
                (latest.c.briefing_date == Briefing.briefing_date)
                & (latest.c.version == Briefing.version),
            )
            .join(StrategyRun, StrategyRun.id == Briefing.strategy_id)
            .order_by(Briefing.briefing_date.desc())
        )
        .tuples()
        .all()
    )
    raw_claims: list[BoardClaim] = []
    persona_rows: list[tuple[str, dict[str, Any]]] = []
    for day, report, personas in runs:
        report = report or {}
        for entry in report.get("roadmap") or []:
            raw_claims.append(
                BoardClaim(
                    text=entry.get("text", ""),
                    kind="roadmap",
                    horizon=entry.get("horizon"),
                    briefing_date=day.isoformat(),
                    item_ids=list(entry.get("item_ids") or []),
                )
            )
        for kind in ("opportunities", "risks"):
            for entry in report.get(kind) or []:
                raw_claims.append(
                    BoardClaim(
                        text=entry.get("text", ""),
                        kind=kind[:-1] if kind == "risks" else "opportunity",
                        horizon=None,
                        briefing_date=day.isoformat(),
                        item_ids=list(entry.get("item_ids") or []),
                    )
                )
        if persona:
            persona_rows.extend(
                (day.isoformat(), p) for p in personas or [] if p.get("key") == persona
            )
    persona_items = {i for _, p in persona_rows for i in p.get("item_ids") or []}
    areas = _areas_of(session, {i for c in raw_claims for i in c.item_ids} | persona_items)
    claims_by_area: dict[int, list[BoardClaim]] = defaultdict(list)
    for claim in raw_claims:
        target = _claim_area(claim.item_ids, areas)
        if target is not None and claim.text:
            claims_by_area[target].append(claim)

    nodes = {
        n.id: n
        for n in session.scalars(
            select(TaxNode).where(TaxNode.id.in_(set(counts) | set(claims_by_area)))
        )
    }
    theme_ids = {n.key: n.id for n in nodes.values()}
    reads: dict[int, PersonaRead] = {}
    if persona:
        for _, p in persona_rows:
            for stance in p.get("stances") or []:
                node_id = theme_ids.get(stance.get("theme"))
                if node_id is not None:
                    read = reads.setdefault(node_id, PersonaRead(stances={}, headlines=[]))
                    read.stances[stance["stance"]] = read.stances.get(stance["stance"], 0) + 1
            target = _claim_area(list(p.get("item_ids") or []), areas)
            if target is not None and p.get("headline"):
                read = reads.setdefault(target, PersonaRead(stances={}, headlines=[]))
                if p["headline"] not in read.headlines and len(read.headlines) < 3:
                    read.headlines.append(p["headline"])
    parents = {
        n.id: n
        for n in session.scalars(
            select(TaxNode).where(
                TaxNode.id.in_({n.parent_id for n in nodes.values() if n.parent_id})
            )
        )
    }

    def board_row(node_id: int) -> BoardRow:
        node = nodes[node_id]
        parent = parents.get(node.parent_id) if node.parent_id else None
        claims = claims_by_area.get(node_id, [])
        return BoardRow(
            key=node.key,
            label=node.label,
            field_label=parent.label if parent else "",
            counts={k: counts[node_id][k] for k in IMPACTS},
            evidence={
                k: [
                    Evidence(item_id=r.id, title=r.title, first_seen_at=r.first_seen_at)
                    for r in sorted(
                        best[node_id][k],
                        key=lambda r: (r.relevance or 0, r.first_seen_at),
                        reverse=True,
                    )[:2]
                ]
                for k in IMPACTS
            },
            horizons={
                h: [c for c in claims if c.kind == "roadmap" and c.horizon == h][:3]
                for h in HORIZONS
            },
            claims=[c for c in claims if c.kind != "roadmap"][:4],
            persona=reads.get(node_id),
        )

    candidates = [i for i in set(counts) | set(claims_by_area) if i in nodes]
    if persona:
        candidates = [i for i in candidates if i in reads] or candidates
    ranked = sorted(
        candidates,
        key=lambda i: (
            len(claims_by_area.get(i, [])) > 0,
            counts[i]["opportunity"] + counts[i]["risk"],
            sum(counts[i].values()),
        ),
        reverse=True,
    )[:ROWS]
    return BoardView(
        days=days,
        persona=persona,
        personas=[PersonaOption(key=p.key, name=p.name, group=p.group) for p in PERSONAS],
        rows=[board_row(i) for i in ranked],
    )
