import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.taxonomy.catalog import FIELDS, THEME_KEYS
from news_insight.taxonomy.models import CardLabel, TaxNode, TaxRevision, TaxScheme
from news_insight.taxonomy.seed import backfill_labels, seed_taxonomy
from news_insight.technologies.catalog import load_technologies
from news_insight.technologies.models import Technology
from news_insight.technologies.service import seed_registry
from tests.technologies.test_registry import card_for

pytestmark = pytest.mark.db


def node(db_session: Session, scheme: str, key: str) -> TaxNode:
    return db_session.scalars(
        select(TaxNode).join(TaxScheme).where(TaxScheme.key == scheme, TaxNode.key == key)
    ).one()


def labels(db_session: Session, item_id: int) -> set[tuple[str, str, str]]:
    rows = db_session.execute(
        select(TaxScheme.key, TaxNode.key, CardLabel.source)
        .join(TaxNode, TaxNode.id == CardLabel.node_id)
        .join(TaxScheme, TaxScheme.id == CardLabel.scheme_id)
        .where(CardLabel.item_id == item_id)
    ).tuples()
    return set(rows)


def test_seed_builds_any_depth_trees_and_is_idempotent(db_session: Session) -> None:
    seed_registry(db_session, load_technologies())
    techs = db_session.scalar(text("SELECT count(*) FROM technologies WHERE status <> 'ignored'"))

    first = seed_taxonomy(db_session)

    schemes = {s.key: s for s in db_session.scalars(select(TaxScheme))}
    assert set(schemes) == {"technology", "signal_type", "impact", "scope"}
    assert schemes["technology"].llm_depth == 2 and schemes["signal_type"].max_labels == 1
    tech_nodes = db_session.scalars(
        select(TaxNode).where(TaxNode.scheme_id == schemes["technology"].id)
    ).all()
    assert len(tech_nodes) == len(FIELDS) + len(THEME_KEYS) + techs
    llm = node(db_session, "technology", "llm")
    theme = node(db_session, "technology", "ai__foundation_models")
    field = node(db_session, "technology", "ai")
    assert (field.depth, theme.depth, llm.depth) == (1, 2, 3)
    assert llm.path == [field.id, theme.id, llm.id] and llm.parent_id == theme.id
    assert "대형언어모델" in llm.aliases and llm.attrs["kind"] == "technology"
    assert first.revision_id is not None and first.created == len(tech_nodes) + 10 + 3 + 4

    again = seed_taxonomy(db_session)
    assert (again.created, again.updated, again.revision_id) == (0, 0, None)

    llm.label, llm.edited_in_console = "거대언어모델", True
    db_session.execute(update(Technology).where(Technology.key == "llm").values(label="LLM!"))
    seed_taxonomy(db_session)
    db_session.refresh(llm)
    assert llm.label == "거대언어모델"  # console edits win over the registry
    assert (
        db_session.scalar(select(TaxRevision.id).order_by(TaxRevision.id.desc()).limit(1))
        == first.revision_id
    )


def test_trigger_mirrors_legacy_columns_and_keeps_other_sources(db_session: Session) -> None:
    seed_registry(db_session, load_technologies())
    seed_taxonomy(db_session)
    card = card_for(db_session, ["LLM"])
    db_session.execute(
        update(ItemCard)
        .where(ItemCard.id == card.id)
        .values(field="ai", themes=["ai__foundation_models"], signal_type="launch", impact="watch")
    )
    assert labels(db_session, card.item_id) == {
        ("technology", "ai__foundation_models", "legacy"),
        ("technology", "llm", "rule"),
        ("signal_type", "launch", "legacy"),
        ("impact", "watch", "legacy"),
        ("scope", "dx", "legacy"),
    }
    agents = node(db_session, "technology", "ai__ai_agents")
    db_session.add(
        CardLabel(
            item_id=card.item_id, node_id=agents.id, scheme_id=agents.scheme_id, source="human"
        )
    )
    db_session.flush()

    db_session.execute(
        update(ItemCard).where(ItemCard.id == card.id).values(themes=[], keywords=[])
    )

    assert labels(db_session, card.item_id) == {
        ("technology", "ai", "legacy"),  # no theme left: the field stands in
        ("technology", "ai__ai_agents", "human"),
        ("signal_type", "launch", "legacy"),
        ("impact", "watch", "legacy"),
        ("scope", "dx", "legacy"),
    }


def test_backfill_matches_the_trigger(db_session: Session) -> None:
    seed_registry(db_session, load_technologies())
    seed_taxonomy(db_session)
    card = card_for(db_session, ["LLM", "온디바이스 AI"])
    db_session.execute(
        update(ItemCard)
        .where(ItemCard.id == card.id)
        .values(themes=["ai__on_device_ai"], signal_type="research")
    )
    by_trigger = labels(db_session, card.item_id)

    count = backfill_labels(db_session)

    assert labels(db_session, card.item_id) == by_trigger and count >= len(by_trigger)


def test_schemes_api(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed_taxonomy(db_session)
    retired = node(db_session, "signal_type", "ip")
    retired.status = "deprecated"
    db_session.flush()

    body = console_client.get("/api/admin/taxonomy/schemes", headers=headers).json()

    tech = next(s for s in body["schemes"] if s["key"] == "technology")
    assert tech["level_names"] == ["분야", "테마", "기술"] and tech["llm_depth"] == 2
    assert tech["nodes"][0]["depth"] == 1 and "aliases" in tech["nodes"][0]
    signals = next(s for s in body["schemes"] if s["key"] == "signal_type")
    assert any(n["key"] == "ip" and n["status"] == "deprecated" for n in signals["nodes"])
    assert body["revision"] is not None
