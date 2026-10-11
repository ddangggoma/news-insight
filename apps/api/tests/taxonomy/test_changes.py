from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.taxonomy import registry
from news_insight.taxonomy.changes import ChangeError, ChangeSet, apply, preview, rollback
from news_insight.taxonomy.models import TaxNode, TaxRevision
from news_insight.taxonomy.seed import seed_taxonomy
from news_insight.technologies.catalog import load_technologies
from news_insight.technologies.service import seed_registry
from tests.auth.test_account_api import session_token
from tests.taxonomy.test_schemes import labels, node
from tests.technologies.test_registry import card_for

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def setup(db_session: Session) -> list[ItemCard]:
    seed_registry(db_session, load_technologies())
    seed_taxonomy(db_session)
    registry.use(registry.load(db_session))
    cards = [card_for(db_session, kw) for kw in (["LLM"], ["AI 에이전트"], ["온디바이스 AI"])]
    themes = (
        ["ai__foundation_models"],
        ["ai__ai_agents", "ai__foundation_models"],
        ["ai__on_device_ai"],
    )
    for card, theme in zip(cards, themes, strict=True):
        db_session.execute(
            update(ItemCard).where(ItemCard.id == card.id).values(themes=theme, field="ai")
        )
    return cards


def ops(*items: dict[str, Any], note: str | None = None) -> ChangeSet:
    return ChangeSet.model_validate({"ops": list(items), "note": note})


def themes_of(db_session: Session, card: ItemCard) -> list[str]:
    return list(db_session.scalar(select(ItemCard.themes).where(ItemCard.id == card.id)) or [])


def test_merge_rewrites_columns_moves_children_and_rolls_back(db_session: Session) -> None:
    cards = setup(db_session)
    change = ops(
        {
            "op": "merge_node",
            "scheme": "technology",
            "key": "ai__ai_agents",
            "into": "ai__foundation_models",
        }
    )

    seen = preview(db_session, change, now=NOW)
    assert seen.affected_cards >= 2 and seen.revision_id is None
    assert themes_of(db_session, cards[1]) == [
        "ai__ai_agents",
        "ai__foundation_models",
    ]  # untouched

    done = apply(db_session, change, author="boss", now=NOW)

    assert themes_of(db_session, cards[1]) == ["ai__foundation_models"]
    agents, models = (
        node(db_session, "technology", "ai__ai_agents"),
        node(db_session, "technology", "ai__foundation_models"),
    )
    assert agents.status == "merged" and agents.merged_into_id == models.id
    assert "ai__ai_agents" in models.aliases
    assert node(db_session, "technology", "ai에이전트").parent_id == models.id  # child moved
    assert ("technology", "ai__ai_agents", "legacy") not in labels(db_session, cards[1].item_id)

    rollback(db_session, done.revision_id or 0, author="boss", now=NOW)

    assert themes_of(db_session, cards[1]) == ["ai__ai_agents", "ai__foundation_models"]
    db_session.refresh(agents)
    assert (
        agents.status == "active"
        and node(db_session, "technology", "ai에이전트").parent_id == agents.id
    )
    assert db_session.get(TaxRevision, done.revision_id).status == "rolled_back"


def test_deep_nodes_need_no_llm_but_llm_depth_nodes_can_requeue(db_session: Session) -> None:
    cards = setup(db_session)
    apply(
        db_session,
        ops(
            {
                "op": "create_node",
                "scheme": "technology",
                "key": "agent-runtime",
                "label": "에이전트 런타임",
                "parent": "ai에이전트",
                "aliases": ["AI 에이전트"],
            }
        ),
        author="boss",
        now=NOW,
    )
    assert ("technology", "agent-runtime", "rule") in labels(db_session, cards[1].item_id)
    result = apply(
        db_session,
        ops(
            {
                "op": "create_node",
                "scheme": "technology",
                "key": "ai__world_models",
                "label": "월드 모델",
                "parent": "ai",
                "requeue": True,
            }
        ),
        author="boss",
        now=NOW,
    )
    assert result.requeued_cards == 3
    assert (
        db_session.scalar(select(ItemCard.taxonomy_revision).where(ItemCard.id == cards[0].id))
        == "requeue"
    )
    registry.use(registry.load(db_session))  # a pinned registry does not follow revisions
    assert (
        "world_models(월드 모델)"
        in __import__("news_insight.cards.schemas", fromlist=["x"]).card_instructions()
    )


def test_move_retire_split_and_errors(db_session: Session) -> None:
    cards = setup(db_session)
    with pytest.raises(ChangeError, match="under itself"):
        apply(
            db_session,
            ops(
                {"op": "move_node", "scheme": "technology", "key": "ai", "parent": "ai__ai_agents"}
            ),
            author="b",
            now=NOW,
        )
    moved = apply(
        db_session,
        ops(
            {
                "op": "move_node",
                "scheme": "technology",
                "key": "ai__on_device_ai",
                "parent": "semis",
            }
        ),
        author="b",
        now=NOW,
    )
    on_device = node(db_session, "technology", "ai__on_device_ai")
    assert (
        on_device.path[0] == node(db_session, "technology", "semis").id
        and moved.affected_cards >= 1
    )

    apply(
        db_session,
        ops({"op": "retire_node", "scheme": "technology", "key": "ai__on_device_ai"}),
        author="b",
        now=NOW,
    )
    # the move made the card's field follow the theme to semis; retiring the theme keeps it
    assert themes_of(db_session, cards[2]) == [] and ("technology", "semis", "legacy") in labels(
        db_session, cards[2].item_id
    )

    split = apply(
        db_session,
        ops(
            {
                "op": "split_node",
                "scheme": "technology",
                "key": "ai__foundation_models",
                "parts": [{"key": "ai__llm", "label": "LLM"}, {"key": "ai__slm", "label": "SLM"}],
            }
        ),
        author="b",
        now=NOW,
    )
    assert split.requeued_cards == 2 and themes_of(db_session, cards[0]) == []
    with pytest.raises(ChangeError, match="cannot be switched off"):
        apply(
            db_session,
            ops({"op": "update_scheme", "key": "impact", "status": "inactive"}),
            author="b",
            now=NOW,
        )


def test_new_scheme_with_relations_derives_labels(db_session: Session) -> None:
    cards = setup(db_session)
    apply(
        db_session,
        ops(
            {
                "op": "create_scheme",
                "key": "domain",
                "name": "응용 도메인",
                "structure": "list",
                "assign": ["llm", "derived"],
            },
            {"op": "create_node", "scheme": "domain", "key": "mobile", "label": "모바일"},
            {
                "op": "add_relation",
                "from_scheme": "technology",
                "from_key": "ai__on_device_ai",
                "to_scheme": "domain",
                "to_key": "mobile",
            },
        ),
        author="boss",
        now=NOW,
    )
    assert ("domain", "mobile", "derived") in labels(db_session, cards[2].item_id)
    assert ("domain", "mobile", "derived") not in labels(db_session, cards[0].item_id)


def test_console_change_api_needs_an_admin_session(
    console_client: TestClient,
    headers: dict[str, str],
    db_session: Session,
    api: Any,
    boss: Any,
) -> None:
    setup(db_session)
    body = {
        "ops": [{"op": "update_node", "scheme": "technology", "key": "ai", "label": "AI·에이전트"}],
        "note": "이름",
    }
    assert (
        console_client.post("/api/admin/taxonomy/preview", json=body, headers=headers).status_code
        == 401
    )
    admin = {**headers, "X-Session-Token": session_token(api)}

    seen = console_client.post("/api/admin/taxonomy/preview", json=body, headers=admin).json()
    done = console_client.post("/api/admin/taxonomy/apply", json=body, headers=admin).json()
    bad = console_client.post(
        "/api/admin/taxonomy/apply",
        json={"ops": [{"op": "merge_node", "scheme": "technology", "key": "ai", "into": "nope"}]},
        headers=admin,
    )
    revisions = console_client.get("/api/admin/taxonomy/revisions", headers=headers).json()
    counts = console_client.get(
        "/api/admin/taxonomy/counts", headers=headers, params={"days": 365}
    ).json()
    ai = node(db_session, "technology", "ai")
    cards = console_client.get(f"/api/admin/taxonomy/nodes/{ai.id}/cards", headers=headers).json()

    assert seen["revision_id"] is None and done["revision_id"] is not None
    assert bad.status_code == 409 and "unknown node" in bad.text
    assert revisions[0]["author"] == "boss" and revisions[0]["note"] == "이름"
    assert counts[str(ai.id)]["total"] == 3 and len(cards) == 3
    assert ai.label == "AI·에이전트"


def field_of(db_session: Session, card: ItemCard) -> str | None:
    return db_session.scalar(select(ItemCard.field).where(ItemCard.id == card.id))


def test_drag_moves_carry_the_card_columns_and_roll_back(db_session: Session) -> None:
    cards = setup(db_session)
    on_device = cards[2]  # themes ["ai__on_device_ai"], field "ai"

    # a theme dropped under another field: its cards' field follows
    moved = apply(
        db_session,
        ops(
            {
                "op": "move_node",
                "scheme": "technology",
                "key": "ai__on_device_ai",
                "parent": "semis",
            }
        ),
        author="b",
        now=NOW,
    )
    assert field_of(db_session, on_device) == "semis"
    assert themes_of(db_session, on_device) == ["ai__on_device_ai"]
    assert "분야·테마 열 갱신" in moved.outcomes[0].summary
    assert ("technology", "ai__on_device_ai", "legacy") in labels(db_session, on_device.item_id)

    # dropped at the top level: it is a field now, no longer a theme
    apply(
        db_session,
        ops({"op": "move_node", "scheme": "technology", "key": "ai__on_device_ai", "parent": None}),
        author="b",
        now=NOW,
    )
    assert field_of(db_session, on_device) == "ai__on_device_ai"
    assert themes_of(db_session, on_device) == []
    assert node(db_session, "technology", "ai__on_device_ai").depth == 1

    # rolling back the last move restores both the tree and the columns
    last = db_session.scalars(select(TaxRevision).order_by(TaxRevision.id.desc())).first()
    assert last is not None
    rollback(db_session, last.id, author="b", now=NOW)
    assert node(db_session, "technology", "ai__on_device_ai").depth == 2
    assert field_of(db_session, on_device) == "semis"
    assert themes_of(db_session, on_device) == ["ai__on_device_ai"]


def test_a_drop_between_siblings_renumbers_their_order(db_session: Session) -> None:
    setup(db_session)
    parent_id = node(db_session, "technology", "ai").id
    siblings = sorted(
        db_session.scalars(select(TaxNode).where(TaxNode.parent_id == parent_id)),
        key=lambda n: (n.sort, n.label),
    )
    first, last = siblings[0], siblings[-1]
    apply(
        db_session,
        ops(
            {
                "op": "move_node",
                "scheme": "technology",
                "key": last.key,
                "parent": "ai",
                "before": first.key,
            }
        ),
        author="b",
        now=NOW,
    )
    order = sorted(
        (node(db_session, "technology", s.key) for s in siblings), key=lambda n: (n.sort, n.label)
    )
    assert [n.key for n in order[:2]] == [last.key, first.key]
    with pytest.raises(ChangeError, match="not under the new parent"):
        apply(
            db_session,
            ops(
                {
                    "op": "move_node",
                    "scheme": "technology",
                    "key": last.key,
                    "parent": "semis",
                    "before": first.key,
                }
            ),
            author="b",
            now=NOW,
        )


def test_a_merge_across_fields_moves_the_field_and_rolls_back(db_session: Session) -> None:
    cards = setup(db_session)
    on_device = cards[2]  # themes ["ai__on_device_ai"], field "ai"
    merged = apply(
        db_session,
        ops(
            {
                "op": "merge_node",
                "scheme": "technology",
                "key": "ai__on_device_ai",
                "into": "semis__ap_soc_npu",
            }
        ),
        author="b",
        now=NOW,
    )
    assert themes_of(db_session, on_device) == ["semis__ap_soc_npu"]
    assert field_of(db_session, on_device) == "semis"
    assert "분야·테마 열 갱신" in merged.outcomes[0].summary
    assert merged.revision_id is not None
    rollback(db_session, merged.revision_id, author="b", now=NOW)
    assert themes_of(db_session, on_device) == ["ai__on_device_ai"]
    assert field_of(db_session, on_device) == "ai"
