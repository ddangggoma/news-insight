from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.cards.schemas import Classification
from news_insight.collect.contracts import RawItem
from news_insight.companies.catalog import (
    CompanyCatalog,
    Relation,
    load_companies,
    seed_alias_map,
)
from news_insight.companies.models import Company
from news_insight.companies.service import (
    candidates,
    canonical_keys,
    recompute_all,
    seed_registry,
)
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.taxonomy.catalog import THEME_KEYS
from tests.factories import build_source

NOW = datetime(2026, 10, 10, tzinfo=UTC)


def test_bundled_seed_covers_every_theme() -> None:
    catalog = load_companies()
    assert len(catalog.companies) >= 400
    covered = {theme for entry in catalog.companies for theme in entry.themes}
    assert covered == set(THEME_KEYS)
    for theme in THEME_KEYS:  # "major companies per theme": at least six each
        assert sum(theme in entry.themes for entry in catalog.companies) >= 6, theme


def test_catalog_rejects_ambiguous_names_and_unknown_themes() -> None:
    with pytest.raises(ValidationError, match="maps to"):
        CompanyCatalog.model_validate(
            {
                "companies": [
                    {"key": "aa", "name": "A", "aliases": ["Same Name"]},
                    {"key": "bb", "name": "B", "aliases": ["same-name"]},
                ]
            }
        )
    with pytest.raises(ValidationError, match="unknown themes"):
        CompanyCatalog.model_validate(
            {"companies": [{"key": "aa", "name": "A", "themes": ["ai__nothing"]}]}
        )


def test_names_alias_and_translations_resolve_and_short_words_do_not() -> None:
    aliases = seed_alias_map()
    assert canonical_keys(
        ["Samsung Electronics", "삼성전자", "TSMC", "台积电", "Unknown Startup"], aliases
    ) == ["samsungelectronics", "tsmc"]
    assert "롬" not in aliases and "델" not in aliases  # one-syllable words


def test_classification_keeps_up_to_five_distinct_companies() -> None:
    draft = Classification.model_validate(
        {"id": 1, "companies": ["  Apple ", "apple", "#OpenAI", "A", "B", "C", "D"]}
    )
    assert draft.companies == ["Apple", "OpenAI", "A", "B", "C"]


_serial = iter(range(10_000))


def card_for(
    db_session: Session,
    *,
    companies: list[str] | None = None,
    keywords: list[str] | None = None,
    source_key: str = "example-news",
    seen: datetime = NOW,
) -> ItemCard:
    from news_insight.sources.models import Source

    source = db_session.scalars(select(Source).where(Source.key == source_key)).first()
    if source is None:
        source = build_source(key=source_key)
        db_session.add(source)
        db_session.flush()
    url = f"https://www.example.com/company-{next(_serial)}"
    ingest_items(
        db_session,
        source,
        [RawItem(stable_id=url, url=url, title="t")],
        fetch_run=None,
        now=seen,
        canary=True,
    )
    item = db_session.scalars(select(Item).where(Item.url == url)).one()
    card = ItemCard(
        item_id=item.id,
        status=CardStatus.READY,
        title_ko="카드",
        summary_ko=[],
        keywords=keywords or [],
        companies=companies or [],
        input_hash=item.content_hash,
        generated_at=seen,
        scope="dx",
    )
    db_session.add(card)
    db_session.flush()
    db_session.refresh(card)
    return card


@pytest.mark.db
def test_trigger_tags_registered_companies_from_engine_list_and_keywords(
    db_session: Session,
) -> None:
    card = card_for(
        db_session,
        companies=["Qualcomm", "Some New Robotics"],
        keywords=["스냅드래곤", "삼성전자", "온디바이스 AI"],
    )
    assert card.company_keys == ["qualcomm", "samsungelectronics"]

    db_session.execute(update(ItemCard).where(ItemCard.id == card.id).values(companies=["TSMC"]))
    db_session.refresh(card)
    assert card.company_keys == ["tsmc", "qualcomm", "samsungelectronics"]


@pytest.mark.db
def test_seed_keeps_console_edits_and_recompute_applies_new_aliases(db_session: Session) -> None:
    company = db_session.get(Company, "openai")
    assert company is not None
    company.relation, company.edited_in_console = Relation.COMPETITOR, True
    db_session.flush()
    card = card_for(db_session, keywords=["Some New Robotics"])
    assert card.company_keys == []

    catalog = load_companies()
    catalog.companies.append(
        catalog.companies[0].model_copy(
            update={
                "key": "somenewrobotics",
                "name": "Some New Robotics",
                "name_ko": None,
                "aliases": [],
            }
        )
    )
    result = seed_registry(db_session, catalog)
    changed = recompute_all(db_session)

    db_session.refresh(card)
    assert result.created == 1 and company.relation is Relation.COMPETITOR
    assert changed >= 1 and card.company_keys == ["somenewrobotics"]


@pytest.mark.db
def test_candidates_are_unregistered_names_with_new_entrants_marked(db_session: Session) -> None:
    for source in ("news-a", "news-b", "news-c"):
        card_for(db_session, companies=["Nova Haptics", "Apple"], source_key=source)
    card_for(db_session, companies=["Old Widget Co"], source_key="news-a")
    card_for(db_session, companies=["Old Widget Co"], source_key="news-b")
    card_for(db_session, companies=["Old Widget Co"], source_key="news-c")
    card_for(
        db_session, companies=["Old Widget Co"], source_key="news-a", seen=NOW - timedelta(days=60)
    )
    card_for(db_session, companies=["Lonely Corp"], source_key="news-a")

    rows = {row.key: row for row in candidates(db_session, now=NOW + timedelta(hours=1))}

    assert set(rows) == {"novahaptics", "oldwidgetco"}  # Apple is registered, Lonely is thin
    assert rows["novahaptics"].earlier == 0 and rows["novahaptics"].sources == 3
    assert rows["oldwidgetco"].earlier == 1 and rows["novahaptics"].name == "Nova Haptics"


@pytest.mark.db
def test_backfill_queues_recent_cards_without_companies_and_keeps_them_visible(
    db_session: Session,
) -> None:
    from news_insight.cards.service import classify_pending_condition
    from news_insight.companies.service import BACKFILL_REVISION, mark_backfill
    from news_insight.public.filters import in_current_tree
    from news_insight.taxonomy.catalog import TAXONOMY_REVISION

    empty = card_for(db_session, keywords=["x"], seen=NOW - timedelta(days=3))
    named = card_for(db_session, companies=["Qualcomm"], seen=NOW - timedelta(days=3))
    old = card_for(db_session, keywords=["y"], seen=NOW - timedelta(days=120))
    for card in (empty, named, old):
        card.taxonomy_revision = TAXONOMY_REVISION
    db_session.flush()

    assert mark_backfill(db_session, now=NOW, days=90, apply=False) == 1
    assert mark_backfill(db_session, now=NOW, days=90) == 1

    db_session.refresh(empty)
    assert empty.taxonomy_revision == BACKFILL_REVISION
    pending = db_session.scalars(
        select(ItemCard.id)
        .join(Item, Item.id == ItemCard.item_id)
        .where(classify_pending_condition(), in_current_tree())
    ).all()
    assert pending == [empty.id]
