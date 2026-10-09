"""Maturity and roadmap (plan 16 #9): where each technology area stands, read from the mix
of signals its cards carry. Research and patents mean early work; standards, ecosystems and
regulation mean the field is organising; launches (and the security events that follow
shipped products) mean products; market, finance and supply news mean diffusion. The index is
the signal-weighted mean stage (1-4), per month for movement, with the companies most often
in the area's cards."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.companies.service import info_for
from news_insight.content.models import Item
from news_insight.public.filters import ReaderFilters, joined
from news_insight.public.periods import KST
from news_insight.public.schemas import CompanyRef
from news_insight.taxonomy.models import CardLabel, TaxNode, TaxScheme

STAGES = ("research", "organising", "product", "diffusion")
STAGE_OF = {
    "research": 1,
    "ip": 1,
    "standard": 2,
    "ecosystem": 2,
    "regulation": 2,
    "launch": 3,
    "security_event": 3,
    "market": 4,
    "finance": 4,
    "supply": 4,
}
MIN_CARDS = 8  # fewer cards than this and the stage is not read


class MonthIndex(BaseModel):
    month: str
    index: float | None
    count: int


class AreaMaturity(BaseModel):
    key: str
    label: str
    field_key: str
    field_label: str
    count: int
    mix: dict[str, float]  # stage -> share of the area's cards
    index: float  # 1 (research) .. 4 (diffusion)
    stage: str
    history: list[MonthIndex]
    companies: list[CompanyRef]


class MaturityView(BaseModel):
    days: int
    fields: list[dict[str, str]]
    areas: list[AreaMaturity]


def _index(counter: Counter[int]) -> float | None:
    total = sum(counter.values())
    return round(sum(stage * n for stage, n in counter.items()) / total, 2) if total else None


def maturity_view(
    session: Session, *, now: datetime, days: int = 180, field: str | None = None
) -> MaturityView:
    since = now - timedelta(days=days)
    area = func.coalesce(TaxNode.path[2], TaxNode.id)
    rows = session.execute(
        joined(
            select(
                area.label("area"),
                Item.id,
                Item.first_seen_at,
                ItemCard.signal_type,
                ItemCard.company_keys,
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
            ItemCard.signal_type.in_(list(STAGE_OF)),
        )
        .distinct()
    ).all()
    stages: dict[int, Counter[int]] = defaultdict(Counter)
    months: dict[int, dict[str, Counter[int]]] = defaultdict(lambda: defaultdict(Counter))
    companies: dict[int, Counter[str]] = defaultdict(Counter)
    for row in rows:
        stage = STAGE_OF[row.signal_type]
        stages[row.area][stage] += 1
        months[row.area][row.first_seen_at.astimezone(KST).strftime("%Y-%m")][stage] += 1
        companies[row.area].update(row.company_keys or [])
    nodes = {n.id: n for n in session.scalars(select(TaxNode).where(TaxNode.id.in_(list(stages))))}
    parents = {
        n.id: n
        for n in session.scalars(
            select(TaxNode).where(
                TaxNode.id.in_([n.parent_id for n in nodes.values() if n.parent_id])
            )
        )
    }
    month_keys = sorted({m for per in months.values() for m in per})[-6:]
    infos = info_for(session, {k for c in companies.values() for k, _ in c.most_common(5)})
    areas: list[AreaMaturity] = []
    for node_id, counter in stages.items():
        node = nodes.get(node_id)
        parent = parents.get(node.parent_id) if node and node.parent_id else None
        total = sum(counter.values())
        if node is None or parent is None or total < MIN_CARDS:
            continue
        if field and parent.key != field:
            continue
        index = _index(counter) or 1.0
        mix = {STAGES[s - 1]: round(counter[s] / total, 3) for s in range(1, 5)}
        areas.append(
            AreaMaturity(
                key=node.key,
                label=node.label,
                field_key=parent.key,
                field_label=parent.label,
                count=total,
                mix=mix,
                index=index,
                stage=STAGES[max(range(4), key=lambda i: mix[STAGES[i]])],
                history=[
                    MonthIndex(
                        month=m,
                        index=_index(months[node_id].get(m, Counter())),
                        count=sum(months[node_id].get(m, Counter()).values()),
                    )
                    for m in month_keys
                ],
                companies=[
                    CompanyRef(
                        key=k,
                        label=infos[k].name_ko or infos[k].name,
                        relation=infos[k].relation,
                        kind=infos[k].kind,
                    )
                    for k, _ in companies[node_id].most_common(5)
                    if k in infos
                ],
            )
        )
    fields = sorted({(a.field_key, a.field_label) for a in areas}, key=lambda f: f[1])
    return MaturityView(
        days=days,
        fields=[{"key": k, "label": label} for k, label in fields],
        areas=sorted(areas, key=lambda a: (a.index, -a.count)),
    )
