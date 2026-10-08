import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.cards.schemas import (
    Classification,
    card_batch_schema,
    card_instructions,
    classify_batch_schema,
)
from news_insight.taxonomy import registry
from news_insight.taxonomy.models import TaxNode, TaxRelation, TaxRevision, TaxScheme
from news_insight.taxonomy.seed import backfill_labels, rebuild_paths, relabel, seed_taxonomy
from news_insight.technologies.catalog import load_technologies
from news_insight.technologies.service import seed_registry
from tests.taxonomy.test_schemes import labels, node
from tests.technologies.test_registry import card_for


def test_code_registry_validates_like_the_old_catalog() -> None:
    draft = Classification.model_validate(
        {
            "id": 1,
            "field": "semis",
            "themes": ["ap_soc_npu", "ai__on_device_ai", "nope", "ai"],
            "signal_type": "launch",
            "impact": "maybe",
            "scope": "dx",
        }
    )
    assert draft.themes == ["semis__ap_soc_npu", "ai__on_device_ai"] and draft.field == "semis"
    assert (draft.signal_type, draft.impact, draft.scope) == ("launch", None, "dx")
    only_field = Classification.model_validate({"id": 2, "themes": ["ai"]})
    assert only_field.themes == [] and only_field.field == "ai"  # a field alone: low confidence
    schema = card_batch_schema()["properties"]["cards"]["items"]
    assert (
        "ai" in schema["properties"]["themes"]["items"]["enum"]
        and "labels" not in schema["properties"]
    )
    assert "semis(반도체·컴퓨팅 HW): ap_soc_npu(모바일 AP·SoC·NPU)" in card_instructions()


def _db_registry(db_session: Session) -> None:
    seed_registry(db_session, load_technologies())
    seed_taxonomy(db_session)
    registry.use(registry.load(db_session))


@pytest.mark.db
def test_deeper_nodes_new_schemes_and_relations_need_no_llm(db_session: Session) -> None:
    _db_registry(db_session)
    agents = node(db_session, "technology", "ai__ai_agents")
    coding = TaxNode(
        scheme_id=agents.scheme_id,
        parent_id=node(db_session, "technology", "ai에이전트").id,
        key="coding-agent",
        label="코딩 에이전트",
        aliases=["codingagent", "코딩에이전트"],
        attrs={},
    )
    domain = TaxScheme(
        key="domain",
        name="응용 도메인",
        structure="list",
        max_labels=2,
        llm_depth=1,
        assign=["llm", "derived"],
    )
    db_session.add_all([coding, domain])
    db_session.flush()
    rebuild_paths(db_session, agents.scheme_id)
    mobile = TaxNode(scheme_id=domain.id, key="mobile", label="모바일", aliases=[], attrs={})
    car = TaxNode(scheme_id=domain.id, key="vehicle", label="차량", aliases=[], attrs={})
    db_session.add_all([mobile, car])
    db_session.flush()
    rebuild_paths(db_session, domain.id)
    db_session.add(
        TaxRelation(
            from_node_id=node(db_session, "technology", "ai__on_device_ai").id, to_node_id=mobile.id
        )
    )
    db_session.add(TaxRevision(note="test", status="applied", changes=[], snapshot={}))
    db_session.flush()
    registry.use(registry.load(db_session))
    assert coding.depth == 4 and coding.path[-2] == node(db_session, "technology", "ai에이전트").id

    card = card_for(db_session, ["AI 에이전트", "Coding Agent", "AI"])
    db_session.execute(
        update(ItemCard)
        .where(ItemCard.id == card.id)
        .values(themes=["ai__on_device_ai"], field="ai", extra_labels={"domain": ["vehicle"]})
    )

    got = labels(db_session, card.item_id)
    assert ("technology", "coding-agent", "rule") in got and (
        "technology",
        "ai에이전트",
        "rule",
    ) in got
    assert ("technology", "ai", "rule") not in got  # keywords never land on LLM-depth nodes
    assert ("domain", "mobile", "derived") in got and ("domain", "vehicle", "llm") in got
    schema = classify_batch_schema()["properties"]["cards"]["items"]["properties"]
    assert schema["labels"]["properties"]["domain"]["items"]["enum"] == ["mobile", "vehicle"]
    assert "labels.domain" in card_instructions()
    draft = Classification.model_validate(
        {"id": 1, "labels": {"domain": ["vehicle", "mars", "mobile", "vehicle"]}}
    )
    assert draft.labels == {"domain": ["vehicle", "mobile"]}


@pytest.mark.db
def test_backfill_relabels_in_chunks_and_keeps_human_labels(db_session: Session) -> None:
    _db_registry(db_session)
    cards = [card_for(db_session, ["LLM"]) for _ in range(3)]
    for card in cards:
        db_session.execute(
            update(ItemCard).where(ItemCard.id == card.id).values(themes=["ai__foundation_models"])
        )
    before = [labels(db_session, c.item_id) for c in cards]
    db_session.execute(
        __import__("sqlalchemy").text("DELETE FROM card_labels WHERE item_id = :i"),
        {"i": cards[0].item_id},
    )

    backfill_labels(db_session, chunk=2)
    relabel(db_session, [])

    assert [labels(db_session, c.item_id) for c in cards] == before
    assert db_session.scalar(select(TaxScheme.assign).where(TaxScheme.key == "technology")) == [
        "llm",
        "rule",
        "derived",
    ]
