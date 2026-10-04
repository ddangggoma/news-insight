from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.technologies.catalog import (
    TechCatalog,
    load_technologies,
    normalize,
)
from news_insight.technologies.models import Technology
from news_insight.technologies.service import canonical_keys, seed_registry
from tests.factories import build_source


def test_bundled_seed_is_valid_and_large() -> None:
    catalog = load_technologies()
    assert len(catalog.technologies) >= 250
    assert all(entry.theme and "__" in entry.theme for entry in catalog.technologies)


def test_catalog_rejects_ambiguous_aliases() -> None:
    with pytest.raises(ValidationError, match="maps to"):
        TechCatalog.model_validate(
            {
                "technologies": [
                    {"key": "a", "label": "A", "aliases": ["x"]},
                    {"key": "b", "label": "B", "aliases": ["X"]},
                ]
            }
        )
    with pytest.raises(ValidationError, match="normalised"):
        TechCatalog.model_validate({"technologies": [{"key": "Wi Fi", "label": "Wi-Fi"}]})


def test_python_twin_matches_normalisation() -> None:
    assert normalize("  #On-Device AI ") == "ondeviceai"
    assert canonical_keys(
        ["On-device AI", "온디바이스 AI", " "], {"ondeviceai": "온디바이스ai"}
    ) == ["온디바이스ai"]


_serial = iter(range(10_000))


def card_for(db_session: Session, keywords: list[str]) -> ItemCard:
    from news_insight.sources.models import Source

    source = db_session.scalars(select(Source).where(Source.key == "example-news")).first()
    if source is None:
        source = build_source()
        db_session.add(source)
        db_session.flush()
    url = f"https://www.example.com/card-{next(_serial)}"
    ingest_items(
        db_session,
        source,
        [RawItem(stable_id=url, url=url, title="t")],
        fetch_run=None,
        now=datetime.now(UTC),
        canary=True,
    )
    item = db_session.scalars(select(Item).where(Item.url == url)).one()
    card = ItemCard(
        item_id=item.id,
        status=CardStatus.READY,
        title_ko="카드",
        summary_ko=[],
        keywords=keywords,
        input_hash=item.content_hash,
        generated_at=datetime.now(UTC),
        scope="dx",
    )
    db_session.add(card)
    db_session.flush()
    db_session.refresh(card)
    return card


@pytest.mark.db
def test_trigger_derives_keys_on_insert_and_bulk_update(db_session: Session) -> None:
    card = card_for(db_session, ["AI-Agent", "Matter 1.5", "matter1.5", "LLM"])
    assert card.technology_keys == ["ai에이전트", "matter1.5", "llm"]

    db_session.execute(
        update(ItemCard).where(ItemCard.id == card.id).values(keywords=["대형 언어 모델"])
    )
    db_session.refresh(card)
    assert card.technology_keys == ["llm"]


@pytest.mark.db
def test_seed_keeps_console_edits(db_session: Session) -> None:
    tech = db_session.get(Technology, "llm")
    assert tech is not None
    tech.label, tech.edited_in_console = "거대 언어모델", True
    db_session.flush()

    result = seed_registry(db_session, load_technologies())

    assert result.created == 0 and tech.label == "거대 언어모델"


@pytest.mark.db
def test_console_edit_rekeys_cards_and_candidates(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    for _ in range(3):
        card_for(db_session, ["Neural Radiance Field"])
    card = card_for(db_session, ["NeRF"])
    candidates = console_client.get(
        "/api/admin/technologies/candidates", params={"min_count": 3}, headers=headers
    ).json()
    assert {"key": "neuralradiancefield", "label": "Neural Radiance Field", "count": 3} in [
        {k: c[k] for k in ("key", "label", "count")} for c in candidates
    ] or candidates[0]["key"] == "neuralradiancefield"

    created = console_client.post(
        "/api/admin/technologies",
        json={
            "label": "NeRF",
            "theme_key": "display_av__xr_spatial",
            "aliases": ["Neural Radiance Field"],
        },
        headers=headers,
    )
    assert created.status_code == 201 and created.json() == {"key": "nerf"}
    db_session.refresh(card)
    rekeyed = db_session.execute(
        text("select count(*) from item_cards where technology_keys @> '[\"nerf\"]'")
    ).scalar()
    assert card.technology_keys == ["nerf"] and rekeyed == 4

    clash = console_client.patch(
        "/api/admin/technologies/llm", json={"add_aliases": ["NeRF"]}, headers=headers
    )
    assert clash.status_code == 409
    listed = console_client.get(
        "/api/admin/technologies", params={"q": "radiance"}, headers=headers
    ).json()
    assert listed[0]["key"] == "nerf" and listed[0]["cards_30d"] == 4
