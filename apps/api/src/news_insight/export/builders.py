"""Briefings and dossiers as export documents (plan 16 #11)."""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.content.models import Item
from news_insight.dossiers.service import STANCES, DossierDetail
from news_insight.export.document import Block, Doc, Section, Source
from news_insight.public.briefings import PublicBriefing
from news_insight.public.periodic import PublicPeriodic
from news_insight.sources.models import Source as SourceRow
from news_insight.strategy.personas import DEFAULT_PERSONA

HORIZON = {"1y": "1년", "3y": "3년", "5y": "5년"}
STANCE = {"support": "찬성", "oppose": "반대", "context": "참고"}
STATUS = {"open": "검토 중", "supported": "지지됨", "refuted": "기각됨", "mixed": "엇갈림"}
TRAJECTORY = {
    "new": "새로",
    "growing": "커짐",
    "steady": "유지",
    "holding": "유지",
    "quieting": "잦아듦",
    "turning": "반전",
    "turning_around": "반전",
}


def sources_for(session: Session, ids: Iterable[int]) -> dict[int, Source]:
    wanted = set(ids)
    if not wanted:
        return {}
    rows = session.execute(
        select(Item.id, func.coalesce(ItemCard.title_ko, Item.title), Item.url, SourceRow.name)
        .join(SourceRow, SourceRow.id == Item.source_id)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .where(Item.id.in_(wanted))
    ).tuples()
    return {i: Source(item_id=i, title=t, url=u, source=s) for i, t, u, s in rows}


def _horizon(entry: dict[str, Any]) -> str:
    raw = str(entry.get("horizon", ""))
    return HORIZON.get(raw, raw)


def _hypothesis_line(h: Any) -> str:
    support, oppose = h.counts.get("support", 0), h.counts.get("oppose", 0)
    return f"{h.text} — {STATUS.get(h.status, h.status)} (찬성 {support} · 반대 {oppose})"


def _claims(entries: list[dict[str, Any]] | None, label: str = "") -> list[Block]:
    return [
        Block(text=f"{label}{e.get('text', '')}", refs=list(e.get("item_ids") or []), bullet=True)
        for e in entries or []
        if e.get("text")
    ]


def from_briefing(session: Session, briefing: PublicBriefing) -> Doc:
    sections = [
        Section(
            "요약",
            [Block(text=line, bullet=True) for line in briefing.tldr]
            + ([Block(text=briefing.overview)] if briefing.overview else []),
        ),
        Section(
            "핵심 인사이트",
            [
                block
                for insight in briefing.insights
                for block in (
                    Block(text=insight.title, heading=True),
                    Block(text=insight.body, refs=list(insight.item_ids)),
                )
            ],
        ),
    ]
    strategy = briefing.strategy
    report = (strategy.report if strategy else None) or {}
    if report:
        blocks = [Block(text=str(report.get("summary", "")))]
        for field in report.get("fields") or []:
            blocks.append(Block(text=str(field.get("field", "")), heading=True))
            if field.get("summary"):
                blocks.append(Block(text=str(field["summary"])))
            blocks += _claims(field.get("claims"))
        sections.append(Section("전략 보고서", [b for b in blocks if b.text]))
        roadmap = [
            Block(
                text=f"[{_horizon(e)}] {e.get('text', '')}",
                refs=list(e.get("item_ids") or []),
                bullet=True,
            )
            for e in report.get("roadmap") or []
        ]
        if roadmap:
            sections.append(Section("로드맵", roadmap))
        risks = _claims(report.get("opportunities"), "기회: ") + _claims(
            report.get("risks"), "위험: "
        )
        if risks:
            sections.append(Section("기회와 위험", risks))
    if strategy:
        chosen = sorted(
            (p for p in strategy.personas if p.status == "insight"),
            key=lambda p: (p.key != DEFAULT_PERSONA, -p.relevance),
        )[:6]
        blocks = []
        for persona in chosen:
            blocks.append(Block(text=f"{persona.name} — {persona.headline}", heading=True))
            blocks.append(Block(text=persona.insight, refs=list(persona.item_ids)))
            blocks += [Block(text=a, bullet=True) for a in persona.actions]
        if blocks:
            sections.append(Section("역할별 시사점", blocks))
    ids = {r for s in sections for b in s.blocks for r in b.refs}
    return Doc(
        title=briefing.headline or f"{briefing.briefing_date} 브리핑",
        subtitle=f"DX 인텔리전스 일간 브리핑 · {briefing.briefing_date} (v{briefing.version})",
        sections=[s for s in sections if s.blocks],
        sources=sources_for(session, ids),
    )


def from_periodic(session: Session, periodic: PublicPeriodic) -> Doc:
    content = periodic.content
    sections = [
        Section(
            "요약",
            [Block(text=t, bullet=True) for t in content.tldr] + [Block(text=content.overview)],
        ),
        Section(
            "흐름",
            [
                block
                for trend in content.trends
                for block in (
                    Block(
                        text=f"{trend.title} ({TRAJECTORY.get(trend.trajectory, '유지')})",
                        heading=True,
                    ),
                    Block(text=trend.body, refs=list(trend.item_ids)),
                )
            ],
        ),
        Section(
            "기업",
            [
                Block(text=f"{c.name}: {c.summary}", refs=list(c.item_ids), bullet=True)
                for c in content.companies
            ],
        ),
        Section("다음에 볼 것", [Block(text=t, bullet=True) for t in content.watch_next]),
        Section("할 일", [Block(text=t, bullet=True) for t in content.actions]),
    ]
    ids = {r for s in sections for b in s.blocks for r in b.refs}
    return Doc(
        title=content.headline,
        subtitle=(
            f"DX 인텔리전스 {periodic.label} · {periodic.period_start} ~ {periodic.period_end}"
        ),
        sections=[s for s in sections if s.blocks],
        sources=sources_for(session, ids),
    )


def from_dossier(session: Session, dossier: DossierDetail) -> Doc:
    c = dossier.criteria
    criteria = [
        *(f"의미 검색: {c.statement} (≥{c.min_similarity:.2f})" for _ in [0] if c.statement),
        *(f"기업: {', '.join(x.label for x in c.companies)}" for _ in [0] if c.companies),
        *(f"키워드: {', '.join(c.keywords)}" for _ in [0] if c.keywords),
        *(f"분류: {', '.join(c.nodes)}" for _ in [0] if c.nodes),
        *(f"제외: {', '.join(c.exclude)}" for _ in [0] if c.exclude),
    ]
    changes = dossier.changes
    sections = [
        Section(
            "개요",
            ([Block(text=dossier.description)] if dossier.description else [])
            + [Block(text=line, bullet=True) for line in criteria]
            + [Block(text=f"최근 12주 카드 {dossier.total}건")],
        ),
        Section(
            "최근 7일 바뀐 점",
            [Block(text=f"카드 {changes.recent}건 (직전 7일 {changes.previous}건)")]
            + (
                [
                    Block(
                        text="새로 등장한 기업: "
                        + ", ".join(x.label for x in changes.new_companies)
                    )
                ]
                if changes.new_companies
                else []
            )
            + [Block(text=s.title, refs=[s.item_id], bullet=True) for s in changes.top],
        ),
        Section(
            "가설과 근거",
            [
                block
                for h in dossier.hypotheses
                for block in (
                    Block(
                        text=_hypothesis_line(h),
                        heading=True,
                    ),
                    *(
                        Block(
                            text=f"{STANCE[e.stance]}: {e.title}"
                            + (f" — {e.note}" if e.note else ""),
                            refs=[e.item_id],
                            bullet=True,
                        )
                        for stance in STANCES
                        for e in h.evidence
                        if e.stance == stance
                    ),
                )
            ],
        ),
        Section(
            "타임라인",
            [
                block
                for week in reversed(dossier.timeline)
                if week.top
                for block in (
                    Block(text=f"{week.week} 주 · {week.items}건", heading=True),
                    *(Block(text=s.title, refs=[s.item_id], bullet=True) for s in week.top),
                )
            ][:40],
        ),
        Section(
            "관련 기업",
            [Block(text=f"{x.company.label} {x.count}건", bullet=True) for x in dossier.companies],
        ),
        Section(
            "핵심 수치",
            [Block(text=f.text, refs=[f.item_id], bullet=True) for f in dossier.figures],
        ),
    ]
    ids = {r for s in sections for b in s.blocks for r in b.refs}
    return Doc(
        title=dossier.title,
        subtitle=f"DX 인텔리전스 주제 파일 · {dossier.updated_at:%Y-%m-%d} 기준",
        sections=[s for s in sections if s.blocks],
        sources=sources_for(session, ids),
    )
