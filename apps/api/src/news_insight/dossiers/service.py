"""Topic dossiers (plan 16 #4).

A dossier gathers the cards of one topic by any of its criteria — taxonomy nodes with their
subtrees, registered companies, keywords, or a sentence matched by meaning against the card
embeddings (plan 16 #1) — minus cards whose title has an excluded word. Over that set it shows
a weekly timeline with the widest-reported stories, what changed in the last seven days, the
companies involved and sentences with figures. Hypotheses collect cards as support,
counter-evidence or context; suggestions are the matching cards closest to the hypothesis.
"""

import re
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import ColumnElement, Text, and_, cast, false, func, not_, or_, select
from sqlalchemy.orm import Session

from news_insight.ask.models import CardEmbedding
from news_insight.auth.models import User
from news_insight.cards.models import ItemCard
from news_insight.companies.models import Company
from news_insight.companies.service import alias_map, info_for
from news_insight.content.models import Item
from news_insight.dossiers.models import Dossier, DossierEvidence, DossierHypothesis
from news_insight.public.feed import Sort, feed
from news_insight.public.filters import ReaderFilters, joined
from news_insight.public.periods import KST, Window
from news_insight.public.schemas import CompanyRef, FeedPage
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem
from news_insight.taxonomy.query import parse_ref, under_nodes
from news_insight.technologies.catalog import normalize

Embed = Callable[[list[str]], list[list[float]]]
WINDOW_DAYS = 90
WEEKS = 12
ROW_CAP = 8000
SUGGEST_DAYS = 180
STANCES = ("support", "oppose", "context")
STATUSES = ("open", "supported", "refuted", "mixed")
# a number with a unit people quote: shares, money, capacity, process nodes, counts
FIGURE = re.compile(
    r"\d[\d,.]*\s?(%|퍼센트|배|억|조|만|달러|원|위안|유로|엔|GWh|MWh|GW|MW|nm|TOPS|TB|GB"
    r"|대|명|건|개|곳|년|분기)"
)


class DossierError(ValueError):
    """Bad dossier input (an unknown company, no criteria)."""


def _clean(values: Sequence[str], *, low: int, high: int) -> list[str]:
    out: list[str] = []
    for value in values:
        text = " ".join(value.split())
        if low <= len(text) <= high and text not in out:
            out.append(text)
    return out


class DossierIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    nodes: list[str] = Field(default_factory=list, max_length=20)
    companies: list[str] = Field(default_factory=list, max_length=30)  # names or keys
    keywords: list[str] = Field(default_factory=list, max_length=30)
    exclude: list[str] = Field(default_factory=list, max_length=30)
    statement: str | None = Field(default=None, max_length=500)
    min_similarity: float = Field(default=0.6, ge=0.4, le=0.9)

    @field_validator("nodes")
    @classmethod
    def _nodes(cls, values: list[str]) -> list[str]:
        bad = [v for v in values if parse_ref(v) is None]
        if bad:
            raise ValueError(f"not a scheme:key node: {bad[0]}")
        return list(dict.fromkeys(v.strip() for v in values))

    @field_validator("companies", "keywords", "exclude")
    @classmethod
    def _words(cls, values: list[str]) -> list[str]:
        return _clean(values, low=2, high=60)

    def has_criteria(self) -> bool:
        return bool(self.nodes or self.companies or self.keywords or (self.statement or "").strip())


def resolve_companies(session: Session, names: Sequence[str]) -> list[str]:
    """Registry keys for names, aliases or keys; unknown names are an error."""
    aliases = alias_map(session)
    known = set(session.scalars(select(Company.key).where(Company.key.in_(names))))
    keys: list[str] = []
    unknown: list[str] = []
    for name in names:
        key = name if name in known else aliases.get(normalize(name))
        if key is None:
            unknown.append(name)
        elif key not in keys:
            keys.append(key)
    if unknown:
        raise DossierError(f"등록되지 않은 기업: {', '.join(unknown)}")
    return keys


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _mentions(word: str) -> ColumnElement[bool]:
    pattern = _like(word)
    return or_(
        func.coalesce(ItemCard.title_ko, "").ilike(pattern, escape="\\"),
        Item.title.ilike(pattern, escape="\\"),
        cast(ItemCard.keywords, Text).ilike(pattern, escape="\\"),
    )


def match_condition(dossier: Dossier) -> ColumnElement[bool]:
    parts: list[ColumnElement[bool]] = []
    refs = tuple(ref for value in dossier.nodes or [] if (ref := parse_ref(value)) is not None)
    if refs:
        parts.append(under_nodes(refs))
    if dossier.companies:
        parts.append(or_(*(ItemCard.company_keys.contains([key]) for key in dossier.companies)))
    parts.extend(_mentions(word) for word in dossier.keywords or [])
    if dossier.statement_embedding is not None:
        distance = CardEmbedding.embedding.cosine_distance(dossier.statement_embedding)
        parts.append(
            Item.id.in_(select(CardEmbedding.item_id).where(distance <= 1 - dossier.min_similarity))
        )
    if not parts:
        return false()
    condition = or_(*parts)
    for word in dossier.exclude or []:
        pattern = _like(word)
        condition = and_(
            condition,
            not_(func.coalesce(ItemCard.title_ko, "").ilike(pattern, escape="\\")),
            not_(Item.title.ilike(pattern, escape="\\")),
        )
    return condition


def embed_one(embed: Embed | None, text: str | None) -> Any:
    if embed is None or not (text or "").strip():
        return None
    try:
        return embed([str(text)])[0]
    except Exception:  # noqa: BLE001 - LM Studio down: the sentence waits, other criteria work
        return None


def save(
    session: Session,
    body: DossierIn,
    *,
    user: User,
    embed: Embed | None,
    now: datetime,
    dossier: Dossier | None = None,
) -> Dossier:
    if not body.has_criteria():
        raise DossierError("노드·기업·키워드·문장 중 하나는 있어야 합니다.")
    companies = resolve_companies(session, body.companies)
    statement = (body.statement or "").strip() or None
    if dossier is None:
        dossier = Dossier(created_by=user.id, created_at=now, status="active")
        session.add(dossier)
    if statement != dossier.statement or dossier.statement_embedding is None:
        dossier.statement_embedding = embed_one(embed, statement)
    dossier.title = body.title.strip()
    dossier.description = (body.description or "").strip() or None
    dossier.nodes = body.nodes
    dossier.companies = companies
    dossier.keywords = body.keywords
    dossier.exclude = body.exclude
    dossier.statement = statement
    dossier.min_similarity = body.min_similarity
    dossier.updated_by = user.id
    dossier.updated_at = now
    session.flush()
    return dossier


# --- views --------------------------------------------------------------------------------------


class DossierSummary(BaseModel):
    id: int
    title: str
    description: str | None
    recent: int  # cards in the last 7 days
    total: int  # cards in the last 90 days
    hypotheses: int
    updated_at: datetime
    updated_by: str | None


class Criteria(BaseModel):
    nodes: list[str]
    companies: list[CompanyRef]
    keywords: list[str]
    exclude: list[str]
    statement: str | None
    min_similarity: float
    semantic_active: bool  # the sentence has an embedding (LM Studio answered)


class TimelineStory(BaseModel):
    item_id: int
    title: str
    source_count: int
    first_seen_at: datetime


class TimelineWeek(BaseModel):
    week: date  # Monday, KST
    items: int
    stories: int
    top: list[TimelineStory]


class SignalShift(BaseModel):
    key: str
    now: int
    before: int


class Changes(BaseModel):
    recent: int
    previous: int
    new_companies: list[CompanyRef]
    signals: list[SignalShift]
    top: list[TimelineStory]


class CompanyCount(BaseModel):
    company: CompanyRef
    count: int


class Figure(BaseModel):
    item_id: int
    text: str
    source: str
    first_seen_at: datetime


class EvidenceOut(BaseModel):
    id: int
    item_id: int
    title: str
    source: str
    url: str
    first_seen_at: datetime
    stance: str
    note: str | None
    added_by: str | None


class HypothesisOut(BaseModel):
    id: int
    text: str
    status: str
    counts: dict[str, int]
    evidence: list[EvidenceOut]


class DossierDetail(BaseModel):
    id: int
    title: str
    description: str | None
    criteria: Criteria
    created_by: str | None
    updated_by: str | None
    updated_at: datetime
    total: int
    changes: Changes
    timeline: list[TimelineWeek]
    companies: list[CompanyCount]
    figures: list[Figure]
    hypotheses: list[HypothesisOut]


class Suggestion(BaseModel):
    item_id: int
    title: str
    source: str
    url: str
    first_seen_at: datetime
    similarity: float


def _names(session: Session, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return dict(
        session.execute(select(User.id, User.name).where(User.id.in_(wanted))).tuples().all()
    )


def _refs(session: Session, keys: Sequence[str]) -> dict[str, CompanyRef]:
    return {
        key: CompanyRef(
            key=key, label=info.name_ko or info.name, relation=info.relation, kind=info.kind
        )
        for key, info in info_for(session, set(keys)).items()
    }


def _base(dossier: Dossier) -> list[ColumnElement[bool]]:
    return [*ReaderFilters().conditions(), match_condition(dossier)]


def summaries(session: Session, *, now: datetime) -> list[DossierSummary]:
    dossiers = session.scalars(
        select(Dossier).where(Dossier.status == "active").order_by(Dossier.updated_at.desc())
    ).all()
    hypotheses = dict(
        session.execute(
            select(DossierHypothesis.dossier_id, func.count())
            .where(DossierHypothesis.dossier_id.in_([d.id for d in dossiers]))
            .group_by(DossierHypothesis.dossier_id)
        )
        .tuples()
        .all()
    )
    names = _names(session, {d.updated_by for d in dossiers})
    out: list[DossierSummary] = []
    for dossier in dossiers:
        total, recent = session.execute(
            joined(
                select(
                    func.count(),
                    func.count().filter(Item.first_seen_at >= now - timedelta(days=7)),
                )
            ).where(*_base(dossier), Item.first_seen_at >= now - timedelta(days=WINDOW_DAYS))
        ).one()
        out.append(
            DossierSummary(
                id=dossier.id,
                title=dossier.title,
                description=dossier.description,
                recent=recent,
                total=total,
                hypotheses=hypotheses.get(dossier.id, 0),
                updated_at=dossier.updated_at,
                updated_by=names.get(dossier.updated_by) if dossier.updated_by else None,
            )
        )
    return out


def _monday(moment: datetime) -> date:
    day = moment.astimezone(KST).date()
    return day - timedelta(days=day.weekday())


def _top(rows: Sequence[Any], n: int) -> list[TimelineStory]:
    best: dict[Any, Any] = {}
    for row in rows:
        key = row.story_id if row.story_id is not None else -row.id
        if key not in best:
            best[key] = row  # rows are newest first: the latest report stands for the story
    ranked = sorted(
        best.values(), key=lambda r: (r.source_count or 1, r.relevance or 0), reverse=True
    )
    return [
        TimelineStory(
            item_id=r.id, title=r.title, source_count=r.source_count or 1, first_seen_at=r.seen
        )
        for r in ranked[:n]
    ]


def _figures(rows: Sequence[Any], since: datetime, limit: int = 8) -> list[Figure]:
    out: list[Figure] = []
    seen: set[str] = set()
    recent = sorted(
        (r for r in rows if r.seen >= since), key=lambda r: (r.relevance or 0, r.seen), reverse=True
    )
    for row in recent:
        for sentence in row.summary_ko or []:
            text = str(sentence).strip()
            if not FIGURE.search(text) or text in seen or len(text) > 220:
                continue
            seen.add(text)
            out.append(Figure(item_id=row.id, text=text, source=row.source, first_seen_at=row.seen))
            break  # one sentence per card keeps the list varied
        if len(out) == limit:
            break
    return out


def hypotheses_of(session: Session, dossier_id: int) -> list[HypothesisOut]:
    hypotheses = session.scalars(
        select(DossierHypothesis)
        .where(DossierHypothesis.dossier_id == dossier_id)
        .order_by(DossierHypothesis.sort, DossierHypothesis.id)
    ).all()
    rows = (
        session.execute(
            select(
                DossierEvidence,
                func.coalesce(ItemCard.title_ko, Item.title),
                Source.name,
                Item.url,
                Item.first_seen_at,
            )
            .join(Item, Item.id == DossierEvidence.item_id)
            .join(Source, Source.id == Item.source_id)
            .outerjoin(ItemCard, ItemCard.item_id == Item.id)
            .where(DossierEvidence.hypothesis_id.in_([h.id for h in hypotheses]))
            .order_by(DossierEvidence.created_at.desc())
        )
        .tuples()
        .all()
    )
    names = _names(session, {ev.added_by for ev, *_ in rows})
    by_hypothesis: dict[int, list[EvidenceOut]] = {h.id: [] for h in hypotheses}
    for ev, title, source, url, seen in rows:
        by_hypothesis[ev.hypothesis_id].append(
            EvidenceOut(
                id=ev.id,
                item_id=ev.item_id,
                title=title,
                source=source,
                url=url,
                first_seen_at=seen,
                stance=ev.stance,
                note=ev.note,
                added_by=names.get(ev.added_by) if ev.added_by else None,
            )
        )
    return [
        HypothesisOut(
            id=h.id,
            text=h.text,
            status=h.status,
            counts={s: sum(1 for e in by_hypothesis[h.id] if e.stance == s) for s in STANCES},
            evidence=by_hypothesis[h.id],
        )
        for h in hypotheses
    ]


def detail(session: Session, dossier: Dossier, *, now: datetime) -> DossierDetail:
    this_week = _monday(now)
    first_week = this_week - timedelta(weeks=WEEKS - 1)
    start = datetime.combine(first_week, datetime.min.time(), tzinfo=KST)
    rows = session.execute(
        joined(
            select(
                Item.id,
                func.coalesce(ItemCard.title_ko, Item.title).label("title"),
                Item.first_seen_at.label("seen"),
                StoryItem.story_id,
                Story.source_count,
                ItemCard.relevance,
                ItemCard.company_keys,
                ItemCard.signal_type,
                ItemCard.summary_ko,
                Source.name.label("source"),
            )
        )
        .where(*_base(dossier), Item.first_seen_at >= start, Item.first_seen_at < now)
        .order_by(Item.first_seen_at.desc())
        .limit(ROW_CAP)
    ).all()
    by_week: dict[date, list[Any]] = {}
    for row in rows:
        by_week.setdefault(_monday(row.seen), []).append(row)
    timeline = []
    for index in range(WEEKS):
        week = first_week + timedelta(weeks=index)
        members = by_week.get(week, [])
        stories = {r.story_id if r.story_id is not None else -r.id for r in members}
        timeline.append(
            TimelineWeek(week=week, items=len(members), stories=len(stories), top=_top(members, 3))
        )

    recent_since = now - timedelta(days=7)
    recent = [r for r in rows if r.seen >= recent_since]
    previous = [r for r in rows if now - timedelta(days=14) <= r.seen < recent_since]
    older_companies = {k for r in rows if r.seen < recent_since for k in r.company_keys or []}
    recent_companies = Counter(k for r in recent for k in r.company_keys or [])
    company_counts = Counter(k for r in rows for k in r.company_keys or [])
    new_keys = [k for k, _ in recent_companies.most_common() if k not in older_companies][:8]
    refs = _refs(session, [*company_counts, *dossier.companies])
    signals_now = Counter(r.signal_type for r in recent if r.signal_type)
    signals_before = Counter(r.signal_type for r in previous if r.signal_type)
    signals = sorted(
        (
            SignalShift(key=k, now=signals_now[k], before=signals_before[k])
            for k in set(signals_now) | set(signals_before)
        ),
        key=lambda s: (s.now - s.before, s.now),
        reverse=True,
    )
    names = _names(session, {dossier.created_by, dossier.updated_by})
    return DossierDetail(
        id=dossier.id,
        title=dossier.title,
        description=dossier.description,
        criteria=Criteria(
            nodes=list(dossier.nodes or []),
            companies=[refs[k] for k in dossier.companies or [] if k in refs],
            keywords=list(dossier.keywords or []),
            exclude=list(dossier.exclude or []),
            statement=dossier.statement,
            min_similarity=dossier.min_similarity,
            semantic_active=dossier.statement_embedding is not None,
        ),
        created_by=names.get(dossier.created_by) if dossier.created_by else None,
        updated_by=names.get(dossier.updated_by) if dossier.updated_by else None,
        updated_at=dossier.updated_at,
        total=len(rows),
        changes=Changes(
            recent=len(recent),
            previous=len(previous),
            new_companies=[refs[k] for k in new_keys if k in refs],
            signals=signals[:6],
            top=_top(recent, 3),
        ),
        timeline=timeline,
        companies=[
            CompanyCount(company=refs[k], count=n)
            for k, n in company_counts.most_common(12)
            if k in refs
        ],
        figures=_figures(rows, now - timedelta(days=30)),
        hypotheses=hypotheses_of(session, dossier.id),
    )


def items(
    session: Session, dossier: Dossier, *, now: datetime, sort: Sort, page: int, size: int
) -> FeedPage:
    window = Window(
        kind="dossier", key=f"{WINDOW_DAYS}d", start=now - timedelta(days=WINDOW_DAYS), end=now
    )
    return feed(
        session,
        ReaderFilters(),
        window,
        sort=sort,
        page=page,
        size=size,
        extra=[match_condition(dossier)],
    )


# --- hypotheses ---------------------------------------------------------------------------------


def add_hypothesis(
    session: Session, dossier: Dossier, text: str, *, user: User, embed: Embed | None, now: datetime
) -> DossierHypothesis:
    last = session.scalar(
        select(func.max(DossierHypothesis.sort)).where(DossierHypothesis.dossier_id == dossier.id)
    )
    hypothesis = DossierHypothesis(
        dossier_id=dossier.id,
        text=text.strip(),
        status="open",
        embedding=embed_one(embed, text),
        sort=(last or 0) + 1,
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(hypothesis)
    dossier.updated_at, dossier.updated_by = now, user.id
    session.flush()
    return hypothesis


def suggestions(
    session: Session,
    dossier: Dossier,
    hypothesis: DossierHypothesis,
    *,
    embed: Embed | None,
    now: datetime,
    limit: int = 8,
) -> list[Suggestion]:
    if hypothesis.embedding is None:
        hypothesis.embedding = embed_one(embed, hypothesis.text)
        session.flush()
        if hypothesis.embedding is None:
            return []
    distance = CardEmbedding.embedding.cosine_distance(hypothesis.embedding)
    attached = select(DossierEvidence.item_id).where(DossierEvidence.hypothesis_id == hypothesis.id)
    rows = session.execute(
        joined(
            select(
                Item.id,
                func.coalesce(ItemCard.title_ko, Item.title),
                Source.name,
                Item.url,
                Item.first_seen_at,
                (1 - distance).label("similarity"),
            )
        )
        .join(CardEmbedding, CardEmbedding.item_id == Item.id)
        .where(
            *_base(dossier),
            Item.first_seen_at >= now - timedelta(days=SUGGEST_DAYS),
            Item.id.not_in(attached),
        )
        .order_by(distance)
        .limit(limit)
    ).tuples()
    return [
        Suggestion(
            item_id=item_id,
            title=title,
            source=source,
            url=url,
            first_seen_at=seen,
            similarity=round(float(similarity), 3),
        )
        for item_id, title, source, url, seen, similarity in rows
    ]
