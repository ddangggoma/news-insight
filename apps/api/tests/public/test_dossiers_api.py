from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.ask.service import embed_cards
from news_insight.auth import accounts
from news_insight.auth.accounts import Client
from news_insight.auth.models import Role, User, UserStatus
from news_insight.dossiers.routes import dossier_embedder
from tests.public.seed import NOW, seed_corpus
from tests.public.test_ask_api import fake_embed

pytestmark = pytest.mark.db


@pytest.fixture
def headers(db_session: Session, public_headers: dict[str, str]) -> dict[str, str]:
    now = datetime.now(UTC)
    user = User(
        username="analyst",
        password_hash="x",
        name="분석가",
        role=Role.READER,
        status=UserStatus.ACTIVE,
        created_at=now,
        password_changed_at=now,
    )
    db_session.add(user)
    db_session.flush()
    issued = accounts.issue_session(
        db_session, user, now=now, client=Client(ip=None, user_agent=None)
    )
    return {**public_headers, "X-Session-Token": issued.token}


@pytest.fixture
def client(public_client: TestClient, db_session: Session) -> TestClient:
    seed_corpus(db_session)
    embed_cards(db_session, fake_embed, model="bge", now=NOW, limit=100)
    public_client.app.dependency_overrides[dossier_embedder] = lambda: fake_embed  # type: ignore[attr-defined]
    return public_client


def test_dossier_gathers_cards_by_keyword_and_meaning(
    client: TestClient, headers: dict[str, str]
) -> None:
    by_word = client.post(
        "/api/public/dossiers",
        json={"title": "OLED 보상", "keywords": ["OLED"], "exclude": ["repo"]},
        headers=headers,
    )
    assert by_word.status_code == 201, by_word.text
    body = by_word.json()
    assert body["total"] >= 1 and body["criteria"]["semantic_active"] is False
    assert (
        len(body["timeline"]) == 12 and sum(w["items"] for w in body["timeline"]) == body["total"]
    )

    by_meaning = client.post(
        "/api/public/dossiers",
        json={"title": "에이전트", "statement": "AI 에이전트 운영체제", "min_similarity": 0.8},
        headers=headers,
    ).json()
    assert by_meaning["criteria"]["semantic_active"] is True
    items = client.get(f"/api/public/dossiers/{by_meaning['id']}/items", headers=headers).json()
    titles = [i["title"] for i in items["items"]]
    assert titles and all("agent" in t.lower() or "에이전트" in t for t in titles)

    listing = client.get("/api/public/dossiers", headers=headers).json()
    assert {d["title"] for d in listing} == {"OLED 보상", "에이전트"}
    assert all(d["updated_by"] == "분석가" for d in listing)


def test_hypotheses_collect_evidence_from_suggestions(
    client: TestClient, headers: dict[str, str]
) -> None:
    dossier = client.post(
        "/api/public/dossiers",
        json={"title": "에이전트 OS", "keywords": ["에이전트", "agent"]},
        headers=headers,
    ).json()
    base = f"/api/public/dossiers/{dossier['id']}"
    hypotheses = client.post(
        f"{base}/hypotheses", json={"text": "에이전트 OS가 스마트폰 기본이 된다"}, headers=headers
    ).json()
    hid = hypotheses[0]["id"]
    suggested = client.get(f"{base}/hypotheses/{hid}/suggestions", headers=headers).json()
    assert suggested, "matching cards nearest the hypothesis"
    first = suggested[0]["item_id"]
    after = client.post(
        f"{base}/hypotheses/{hid}/evidence",
        json={"item_id": first, "stance": "support"},
        headers=headers,
    ).json()
    assert after[0]["counts"] == {"support": 1, "oppose": 0, "context": 0}
    # the same card again changes its stance instead of doubling it
    after = client.post(
        f"{base}/hypotheses/{hid}/evidence",
        json={"item_id": first, "stance": "oppose", "note": "반례"},
        headers=headers,
    ).json()
    assert after[0]["counts"]["oppose"] == 1 and after[0]["evidence"][0]["note"] == "반례"
    again = client.get(f"{base}/hypotheses/{hid}/suggestions", headers=headers).json()
    assert first not in [s["item_id"] for s in again]
    patched = client.patch(
        f"{base}/hypotheses/{hid}", json={"status": "mixed"}, headers=headers
    ).json()
    assert patched[0]["status"] == "mixed"
    removed = client.delete(
        f"{base}/evidence/{after[0]['evidence'][0]['id']}", headers=headers
    ).json()
    assert removed[0]["evidence"] == []
    assert client.delete(base, headers=headers).status_code == 204
    assert client.get(base, headers=headers).status_code == 404


def test_rules_and_session(
    client: TestClient, headers: dict[str, str], public_headers: dict[str, str]
) -> None:
    assert client.get("/api/public/dossiers", headers=public_headers).status_code == 401
    empty = client.post("/api/public/dossiers", json={"title": "빈 주제"}, headers=headers)
    assert empty.status_code == 422 and "하나는" in empty.text
    unknown = client.post(
        "/api/public/dossiers", json={"title": "기업", "companies": ["없는회사"]}, headers=headers
    )
    assert unknown.status_code == 422 and "없는회사" in unknown.text
    bad_node = client.post(
        "/api/public/dossiers", json={"title": "노드", "nodes": ["bad"]}, headers=headers
    )
    assert bad_node.status_code == 422
