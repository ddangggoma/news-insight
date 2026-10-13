"""Evidence for a trend report (plan 17 R1): the cards a search plan finds, and statistics.

Cards come in by any of: a plan keyword in the title, Korean title or keywords; a registered
company the plan names; a plan sentence close in meaning (bge-m3 card embeddings, as the ask
page and dossiers use); or the criteria of a dossier the report was started from. Excluded words
keep a card out. One card stands for each story. The writer sees up to EVIDENCE_CAP cards —
the best per week first, so the timeline is not only the last few days — and statistics over
everything matched: weekly counts, companies with their first appearance, the signal mix now
against before, regions and tracks, deals, and per-actor timelines.
"""

import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Integer, Text, bindparam, cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.companies.service import alias_map, info_for
from news_insight.content.models import Item
from news_insight.deals.models import Deal
from news_insight.dossiers.models import Dossier
from news_insight.dossiers.service import matched_ids
from news_insight.public.filters import ReaderFilters, joined
from news_insight.public.periods import KST
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem
from news_insight.technologies.catalog import normalize

Embed = Callable[[list[str]], list[list[float]]]

EVIDENCE_CAP = 110
PER_WEEK = 4  # best cards per week taken first, for an even timeline
MATCH_CAP = 4000  # ids per criterion
SEMANTIC_POOL = 150  # nearest cards per sentence
MIN_SIMILARITY = 0.5  # bge-m3: a topic sentence's 100th closest card scores ~0.5 (plan 16 #4)
SUMMARY_CHARS = 320
ACTOR_TIMELINE = 12


@dataclass
class Plan:
    interpretation: str = ""
    keywords: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    questions: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "interpretation": self.interpretation,
            "keywords": self.keywords,
            "companies": self.companies,
            "people": self.people,
            "queries": self.queries,
            "exclude": self.exclude,
            "questions": self.questions,
        }


def _words(values: Any, *, low: int = 2, high: int = 80, cap: int = 14) -> list[str]:
    out: list[str] = []
    for value in values if isinstance(values, list) else []:
        word = " ".join(str(value).split())
        if low <= len(word) <= high and word.lower() not in {w.lower() for w in out}:
            out.append(word)
    return out[:cap]


def plan_from(structured: dict[str, Any], *, topic: str, brief: str | None) -> Plan:
    """The planner's answer, cleaned; the topic itself always searches too."""
    questions = structured.get("questions") or {}
    plan = Plan(
        interpretation=str(structured.get("interpretation") or "")[:300],
        keywords=_words(structured.get("keywords"), high=60),
        companies=_words(structured.get("companies"), cap=10),
        people=_words(structured.get("people"), high=60, cap=6),
        queries=_words(structured.get("queries"), low=4, high=200, cap=5),
        exclude=_words(structured.get("exclude"), high=40, cap=5),
        questions={
            axis: _words(questions.get(axis), low=4, high=200, cap=3)
            for axis in ("timeline", "landscape", "precedents", "implications")
        }
        if isinstance(questions, dict)
        else {},
    )
    return _with_topic(plan, topic=topic, brief=brief)


def default_plan(topic: str, brief: str | None) -> Plan:
    """When the planner fails: the topic as keyword and sentence."""
    return _with_topic(Plan(interpretation=topic), topic=topic, brief=brief)


def _with_topic(plan: Plan, *, topic: str, brief: str | None) -> Plan:
    if len(topic) <= 40 and topic.lower() not in {k.lower() for k in plan.keywords}:
        plan.keywords.insert(0, topic)
    sentence = topic if not brief else f"{topic}. {brief[:300]}"
    if sentence not in plan.queries:
        plan.queries.insert(0, sentence)
    return plan


@dataclass
class Card:
    id: int
    title: str
    original: str
    url: str
    source: str
    region: str
    track: str
    seen: datetime
    story_id: int | None
    covered_by: int
    relevance: int
    signal: str | None
    impact: str | None
    company_keys: list[str]
    summary: list[str]
    keywords: list[str]
    similarity: float = 0.0
    keyword_hits: int = 0
    company_hit: bool = False

    @property
    def score(self) -> float:
        return (
            0.45 * self.similarity
            + 0.15 * min(self.keyword_hits, 3) / 3
            + 0.15 * self.company_hit
            + 0.15 * min(math.log10(max(self.covered_by, 1)) / math.log10(20), 1.0)
            + 0.10 * self.relevance / 100
        )

    def text(self) -> str:
        return " ".join([self.title, self.original, " ".join(self.keywords)]).lower()


@dataclass
class Pack:
    plan: Plan
    since: datetime
    until: datetime
    corpus_since: date | None
    matched: int  # stories matched (one card each)
    evidence: list[Card]
    stats: dict[str, Any]
    actor_timelines: list[dict[str, Any]]
    unknown_companies: list[str]


def _like(word: str) -> str:
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _keyword_ids(
    session: Session, words: Sequence[str], since: datetime, until: datetime
) -> set[int]:
    if not words:
        return set()
    mentions = or_(
        *(
            or_(
                func.coalesce(ItemCard.title_ko, "").ilike(_like(word), escape="\\"),
                Item.title.ilike(_like(word), escape="\\"),
                cast(ItemCard.keywords, Text).ilike(_like(word), escape="\\"),
            )
            for word in words
        )
    )
    return set(
        session.scalars(
            joined(select(Item.id))
            .where(
                *ReaderFilters().conditions(),
                Item.first_seen_at >= since,
                Item.first_seen_at < until,
                mentions,
            )
            .limit(MATCH_CAP)
        )
    )


def resolve_companies(session: Session, names: Sequence[str]) -> tuple[list[str], list[str]]:
    """Registry keys for the names the registry knows, and the names it does not."""
    aliases = alias_map(session)
    keys: list[str] = []
    unknown: list[str] = []
    for name in names:
        key = aliases.get(normalize(name))
        if key is None:
            unknown.append(name)
        elif key not in keys:
            keys.append(key)
    return keys, unknown


def _company_ids(
    session: Session, keys: Sequence[str], since: datetime, until: datetime
) -> set[int]:
    if not keys:
        return set()
    return set(
        session.scalars(
            joined(select(Item.id))
            .where(
                *ReaderFilters().conditions(),
                Item.first_seen_at >= since,
                Item.first_seen_at < until,
                or_(*(ItemCard.company_keys.contains([key]) for key in keys)),
            )
            .limit(MATCH_CAP)
        )
    )


def _literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


def _semantic(
    session: Session,
    embed: Embed | None,
    sentences: Sequence[str],
    since: datetime,
    until: datetime,
) -> dict[int, float]:
    """Best similarity per card over the plan's sentences; empty when LM Studio is down."""
    if embed is None or not sentences:
        return {}
    try:
        vectors = embed(list(sentences))
    except Exception:  # noqa: BLE001 - the embedding model runs on the host and may be off
        return {}
    best: dict[int, float] = {}
    for vector in vectors:
        rows = session.execute(
            text(
                "SELECT e.item_id, 1 - (e.embedding <=> CAST(:q AS vector))"
                " FROM card_embeddings e JOIN items i ON i.id = e.item_id"
                " WHERE i.first_seen_at >= :since AND i.first_seen_at < :until"
                " ORDER BY e.embedding <=> CAST(:q AS vector) LIMIT :pool"
            ),
            {"q": _literal(vector), "since": since, "until": until, "pool": SEMANTIC_POOL},
        ).all()
        for item_id, similarity in rows:
            if similarity >= MIN_SIMILARITY:
                best[item_id] = max(best.get(item_id, 0.0), float(similarity))
    return best


def _cards(session: Session, ids: set[int]) -> list[Card]:
    if not ids:
        return []
    rows = session.execute(
        joined(
            select(
                Item.id,
                func.coalesce(ItemCard.title_ko, Item.title),
                Item.title,
                Item.url,
                Source.name,
                Source.region,
                Item.track,
                Item.first_seen_at,
                StoryItem.story_id,
                Story.source_count,
                ItemCard.relevance,
                ItemCard.signal_type,
                ItemCard.impact,
                ItemCard.company_keys,
                ItemCard.summary_ko,
                ItemCard.keywords,
            )
        ).where(
            *ReaderFilters().conditions(),
            Item.id == func.any(bindparam("ids", sorted(ids), type_=ARRAY(Integer))),
        )
    ).all()
    return [
        Card(
            id=row[0],
            title=row[1] or row[2],
            original=row[2],
            url=row[3],
            source=row[4],
            region=str(row[5]),
            track=str(row[6]),
            seen=row[7],
            story_id=row[8],
            covered_by=row[9] or 1,
            relevance=row[10] or 0,
            signal=row[11],
            impact=row[12],
            company_keys=list(row[13] or []),
            summary=[str(s) for s in row[14] or []],
            keywords=[str(k) for k in row[15] or []],
        )
        for row in rows
    ]


def _monday(moment: datetime) -> date:
    day = moment.astimezone(KST).date()
    return day - timedelta(days=day.weekday())


def _pick(cards: list[Card]) -> list[Card]:
    """Up to PER_WEEK best cards from every week, then the best of the rest, newest first."""
    ranked = sorted(cards, key=lambda c: c.score, reverse=True)
    chosen: list[Card] = []
    taken: Counter[date] = Counter()
    for card in ranked:
        week = _monday(card.seen)
        if taken[week] < PER_WEEK:
            taken[week] += 1
            chosen.append(card)
    chosen = chosen[:EVIDENCE_CAP]
    ids = {c.id for c in chosen}
    for card in ranked:
        if len(chosen) >= EVIDENCE_CAP:
            break
        if card.id not in ids:
            chosen.append(card)
            ids.add(card.id)
    return sorted(chosen, key=lambda c: c.seen, reverse=True)


def _stats(
    session: Session, cards: list[Card], *, since: datetime, until: datetime
) -> dict[str, Any]:
    days = max((until - since).days, 1)
    recent_since = until - timedelta(days=max(min(14, days // 2), 1))
    weeks: dict[date, Counter[str]] = {}
    for card in cards:
        weeks.setdefault(_monday(card.seen), Counter())["stories"] += 1
    weekly = [
        {"week": week.isoformat(), "stories": weeks[week]["stories"]} for week in sorted(weeks)
    ]
    recent = [c for c in cards if c.seen >= recent_since]
    before = [c for c in cards if c.seen < recent_since]
    signals = sorted(
        {c.signal for c in cards if c.signal},
        key=lambda s: -sum(1 for c in cards if c.signal == s),
    )
    signal_mix = [
        {
            "signal": signal,
            "recent": sum(1 for c in recent if c.signal == signal),
            "before": sum(1 for c in before if c.signal == signal),
        }
        for signal in signals
    ]
    counts: Counter[str] = Counter(key for c in cards for key in c.company_keys)
    info = info_for(session, [key for key, _ in counts.most_common(15)])
    companies = []
    for key, count in counts.most_common(15):
        if key not in info:
            continue
        seen = [c.seen for c in cards if key in c.company_keys]
        companies.append(
            {
                "key": key,
                "name": info[key].name_ko or info[key].name,
                "relation": info[key].relation,
                "kind": info[key].kind,
                "stories": count,
                "recent": sum(1 for c in recent if key in c.company_keys),
                "first_seen": min(seen).astimezone(KST).date().isoformat(),
                "last_seen": max(seen).astimezone(KST).date().isoformat(),
            }
        )
    deals = session.execute(
        select(Deal)
        .where(Deal.item_id.in_([c.id for c in cards]))
        .order_by(Deal.announced_on.desc().nulls_last())
        .limit(20)
    ).scalars()
    return {
        "recent_since": recent_since.astimezone(KST).date().isoformat(),
        "stories": len(cards),
        "weekly": weekly,
        "signal_mix": signal_mix,
        "companies": companies,
        "regions": dict(Counter(c.region for c in cards).most_common()),
        "tracks": dict(Counter(c.track for c in cards).most_common()),
        "impacts": dict(Counter(c.impact for c in cards if c.impact).most_common()),
        "deals": [
            {
                "kind": d.kind,
                "actor": d.actor,
                "counterparty": d.counterparty,
                "amount_usd": d.amount_usd,
                "stage": d.stage,
                "announced_on": d.announced_on.isoformat() if d.announced_on else None,
                "item_id": d.item_id,
            }
            for d in deals
        ],
    }


def _actor_timelines(
    cards: list[Card], plan: Plan, keys: list[str], names: dict[str, str]
) -> list[dict[str, Any]]:
    """Each named person and company with its matching cards, oldest first."""
    actors: list[tuple[str, str | None, str | None]] = [
        (person, person.lower(), None) for person in plan.people
    ]
    actors += [(names.get(key, key), None, key) for key in keys[:6]]
    out = []
    for label, name, key in actors:
        hits = sorted(
            (
                c
                for c in cards
                if (name is not None and name in c.text()) or (key and key in c.company_keys)
            ),
            key=lambda c: c.seen,
        )
        if hits:
            out.append(
                {
                    "actor": label,
                    "cards": [
                        {
                            "id": c.id,
                            "date": c.seen.astimezone(KST).date().isoformat(),
                            "title": c.title,
                        }
                        for c in hits[-ACTOR_TIMELINE:]
                    ],
                }
            )
    return out


def gather(
    session: Session,
    plan: Plan,
    *,
    days: int,
    now: datetime,
    embed: Embed | None,
    dossier: Dossier | None = None,
) -> Pack:
    since, until = now - timedelta(days=days), now
    keys, unknown = resolve_companies(session, plan.companies)
    keyword_ids = _keyword_ids(session, [*plan.keywords, *plan.people], since, until)
    company_ids = _company_ids(session, keys, since, until)
    similar = _semantic(session, embed, plan.queries, since, until)
    ids = keyword_ids | company_ids | set(similar)
    if dossier is not None:
        ids |= set(matched_ids(session, dossier, since=since, until=until)[:MATCH_CAP])
    cards = _cards(session, ids)
    excluded = [word.lower() for word in plan.exclude]
    terms = [word.lower() for word in [*plan.keywords, *plan.people]]
    kept: list[Card] = []
    for card in cards:
        if any(word in card.title.lower() or word in card.original.lower() for word in excluded):
            continue
        card.similarity = similar.get(card.id, 0.0)
        body = card.text()
        card.keyword_hits = sum(1 for term in terms if term in body)
        card.company_hit = any(key in card.company_keys for key in keys)
        kept.append(card)
    # one card per story: the best scored stands for it
    by_story: dict[int, Card] = {}
    for card in kept:
        story = card.story_id if card.story_id is not None else -card.id
        if story not in by_story or card.score > by_story[story].score:
            by_story[story] = card
    stories = list(by_story.values())
    names = {key: info.name_ko or info.name for key, info in info_for(session, keys).items()}
    first = session.scalar(select(func.min(Item.first_seen_at)))
    return Pack(
        plan=plan,
        since=since,
        until=until,
        corpus_since=first.astimezone(KST).date() if first else None,
        matched=len(stories),
        evidence=_pick(stories),
        stats=_stats(session, stories, since=since, until=until),
        actor_timelines=_actor_timelines(stories, plan, keys, names),
        unknown_companies=unknown,
    )


def payload(pack: Pack, *, topic: str, brief: str | None) -> dict[str, Any]:
    """What the writer reads."""
    return {
        "topic": topic,
        "brief": brief or "",
        "period": {
            "from": pack.since.astimezone(KST).date().isoformat(),
            "to": pack.until.astimezone(KST).date().isoformat(),
        },
        "corpus_since": pack.corpus_since.isoformat() if pack.corpus_since else None,
        "plan": {
            "interpretation": pack.plan.interpretation,
            "questions": pack.plan.questions,
            "companies_not_registered": pack.unknown_companies,
        },
        "matched_stories": pack.matched,
        "evidence": [
            {
                "id": c.id,
                "date": c.seen.astimezone(KST).date().isoformat(),
                "source": c.source,
                "region": c.region,
                "track": c.track,
                "signal": c.signal,
                "impact": c.impact,
                "companies": c.company_keys[:5],
                "covered_by": c.covered_by,
                "title": c.title,
                "summary": " ".join(c.summary)[:SUMMARY_CHARS],
            }
            for c in pack.evidence
        ],
        "stats": pack.stats,
        "actor_timelines": pack.actor_timelines,
    }


def sources(pack: Pack) -> dict[str, dict[str, Any]]:
    """Evidence cards by id (JSON keys are strings), for citations and the reference list."""
    return {
        str(c.id): {
            "title": c.title,
            "url": c.url,
            "source": c.source,
            "date": c.seen.astimezone(KST).date().isoformat(),
        }
        for c in pack.evidence
    }
