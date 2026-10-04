"""A small classified corpus for reader API tests (all times relative to NOW)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import Region, Track
from news_insight.stories.models import ItemRef, Relation, Story, StoryItem
from news_insight.taxonomy.catalog import TAXONOMY_REVISION
from tests.factories import build_source

# 2026-10-04 12:00 KST, a Sunday in ISO week 2026-W40
NOW = datetime(2026, 10, 4, 3, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Spec:
    title: str
    source: str
    hours_ago: float
    field: str | None = None
    themes: tuple[str, ...] = ()
    signal_type: str | None = None
    impact: str | None = "watch"
    scope: str | None = "dx"
    relevance: int | None = 50
    keywords: tuple[str, ...] = ()
    status: CardStatus = CardStatus.READY
    revision: str = TAXONOMY_REVISION


SPECS = (
    Spec(
        "Galaxy agent OS",
        "verge",
        2,
        "ai",
        ("ai__ai_agents",),
        "launch",
        "opportunity",
        "dx",
        90,
        ("AI 에이전트", "갤럭시"),
    ),
    Spec(
        "에이전트 OS 국내 보도",
        "etnews",
        5,
        "ai",
        ("ai__ai_agents",),
        "launch",
        "opportunity",
        "dx",
        80,
        ("AI에이전트",),
    ),
    Spec(
        "OLED burn-in compensation",
        "arxiv",
        26,
        "display_av",
        ("display_av__display_panel",),
        "research",
        "opportunity",
        "dx",
        70,
        ("OLED",),
    ),
    Spec(
        "oled-compensation repo",
        "github",
        50,
        "display_av",
        ("display_av__display_panel",),
        "ecosystem",
        "watch",
        "dx",
        60,
        ("oled", "번인"),
    ),
    Spec(
        "HBM capacity expansion",
        "verge",
        30,
        "semis",
        ("semis__memory_storage",),
        "finance",
        "watch",
        "excluded",
        10,
        ("HBM",),
    ),
    Spec(
        "커뮤니티 잡담",
        "geeknews",
        28,
        "platform_sw",
        (),
        None,
        "watch",
        "irrelevant",
        5,
        ("잡담",),
    ),
    Spec(
        "6G radio study items",
        "verge",
        24 * 10,
        "connectivity",
        ("connectivity__cellular_5g_6g",),
        "standard",
        "watch",
        "dx_dependency",
        55,
        ("6G", "AI 에이전트"),
    ),
    Spec("Failed card", "verge", 3, status=CardStatus.FAILED),
    Spec("Stale revision", "verge", 4, "ai", (), None, revision="2000-01-01.0"),
)


def seed_corpus(session: Session) -> dict[str, int]:
    sources = {
        "verge": build_source(key="verge", name="The Verge"),
        "etnews": build_source(
            key="etnews",
            name="전자신문",
            region=Region.KR,
            language="ko",
            official_domain="etnews.com",
        ),
        "arxiv": build_source(
            key="arxiv",
            name="arXiv",
            track=Track.RESEARCH_IP,
            category="academic_paper",
            official_domain="arxiv.org",
        ),
        "github": build_source(
            key="github",
            name="GitHub",
            track=Track.OSS,
            category="oss_trend",
            official_domain="github.com",
        ),
        "geeknews": build_source(
            key="geeknews",
            name="GeekNews",
            region=Region.KR,
            language="ko",
            track=Track.COMMUNITY,
            category="dev_forum",
            official_domain="news.hada.io",
        ),
    }
    session.add_all(sources.values())
    session.flush()
    for spec in SPECS:
        ingest_items(
            session,
            sources[spec.source],
            [
                RawItem(
                    stable_id=spec.title,
                    url=f"https://{spec.source}.example/{len(spec.title)}-{spec.hours_ago}",
                    title=spec.title,
                )
            ],
            fetch_run=None,
            now=NOW - timedelta(hours=spec.hours_ago),
            canary=True,
        )
    items = {item.title: item for item in session.scalars(select(Item))}
    for spec in SPECS:
        item = items[spec.title]
        session.add(
            ItemCard(
                item_id=item.id,
                status=spec.status,
                title_ko=None if spec.status == CardStatus.FAILED else f"[KO] {spec.title}",
                summary_ko=[] if spec.status == CardStatus.FAILED else [f"{spec.title} 요약"],
                keywords=list(spec.keywords),
                engine="agy",
                model="gemini",
                input_hash=item.content_hash,
                attempts=0,
                generated_at=item.first_seen_at,
                field=spec.field,
                themes=list(spec.themes),
                signal_type=spec.signal_type,
                impact=spec.impact,
                scope=spec.scope,
                relevance=spec.relevance,
                taxonomy_revision=spec.revision,
            )
        )
    lead, follow = items["Galaxy agent OS"], items["에이전트 OS 국내 보도"]
    story = Story(
        representative_item_id=lead.id,
        title_ko="[KO] Galaxy agent OS",
        first_seen_at=follow.first_seen_at,
        last_seen_at=lead.first_seen_at,
        item_count=2,
        source_count=2,
        tracks=["news"],
        max_relevance=90,
    )
    session.add(story)
    session.flush()
    session.add_all(
        [
            StoryItem(
                item_id=lead.id,
                story_id=story.id,
                relation=Relation.SEED,
                similarity=None,
                joined_at=lead.first_seen_at,
            ),
            StoryItem(
                item_id=follow.id,
                story_id=story.id,
                relation=Relation.NEAR,
                similarity=0.7,
                joined_at=lead.first_seen_at,
            ),
            ItemRef(
                item_id=items["OLED burn-in compensation"].id, kind="arxiv", value="2610.00001"
            ),
            ItemRef(item_id=items["oled-compensation repo"].id, kind="arxiv", value="2610.00001"),
        ]
    )
    session.flush()
    return {title: item.id for title, item in items.items()}
