from datetime import timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.ask.models import CardEmbedding
from news_insight.ask.service import ask, embed_cards
from news_insight.public.routes import ask_engines
from tests.public.seed import NOW, seed_corpus

pytestmark = pytest.mark.db


def vector_for(text: str) -> list[float]:
    """A deterministic embedding: agent, OLED and everything else point different ways."""
    v = np.full(1024, 0.01)
    lowered = text.lower()
    v[0 if "에이전트" in lowered or "agent" in lowered else 1 if "oled" in lowered else 2] = 1.0
    return [float(x) for x in v / np.linalg.norm(v)]


def fake_embed(texts: list[str]) -> list[list[float]]:
    return [vector_for(t) for t in texts]


def test_answers_from_nearest_cards_with_citations(db_session: Session) -> None:
    seed_corpus(db_session)
    done = embed_cards(db_session, fake_embed, model="bge", now=NOW, limit=100)
    assert done > 0
    assert embed_cards(db_session, fake_embed, model="bge", now=NOW, limit=100) == 0
    prompts: list[str] = []

    def chat(system: str, user: str) -> str:
        prompts.append(user)
        return "에이전트 OS가 출시됐다 [1][2]. 없는 번호 [40]."

    result = ask(
        db_session,
        "에이전트 OS 동향은?",
        days=30,
        node=None,
        embed=fake_embed,
        chat=chat,
        model="qwen",
        now=NOW,
    )
    assert "agent" in result.evidence[0].title.lower() or "에이전트" in result.evidence[0].title
    assert result.cited == [1, 2]
    assert "[1]" in prompts[0] and "질문: 에이전트 OS 동향은?" in prompts[0]
    # irrelevant cards never become evidence
    assert all(e.n == i + 1 for i, e in enumerate(result.evidence))


def test_period_and_node_scope(db_session: Session) -> None:
    seed_corpus(db_session)
    embed_cards(db_session, fake_embed, model="bge", now=NOW, limit=100)
    assert db_session.scalars(select(CardEmbedding)).first() is not None
    calls: list[str] = []

    def chat(system: str, user: str) -> str:
        calls.append(user)
        return "x"

    empty = ask(
        db_session,
        "OLED",
        days=1,
        node="theme:nonexistent",
        embed=fake_embed,
        chat=chat,
        model="qwen",
        now=NOW + timedelta(days=400),
    )
    assert empty.evidence == [] and not calls and "찾지 못했습니다" in empty.answer


def test_route_answers_and_reports_unavailable(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    seed_corpus(db_session)
    embed_cards(db_session, fake_embed, model="bge", now=NOW, limit=100)
    app = public_client.app
    app.dependency_overrides[ask_engines] = lambda: (fake_embed, lambda s, u: "답 [1]", "qwen")  # type: ignore[attr-defined]
    ok = public_client.post(
        "/api/public/ask", json={"question": "OLED 보상 기술", "days": 30}, headers=public_headers
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["cited"] == [1] and body["evidence"][0]["url"].startswith("http")

    def broken(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("down")

    app.dependency_overrides[ask_engines] = lambda: (broken, lambda s, u: "", "qwen")  # type: ignore[attr-defined]
    down = public_client.post("/api/public/ask", json={"question": "OLED"}, headers=public_headers)
    assert down.status_code == 503
    assert public_client.post("/api/public/ask", json={"question": "x"}).status_code in (401, 403)
