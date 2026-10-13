from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.ask.service import embed_cards
from news_insight.auth import accounts
from news_insight.auth.accounts import Client
from news_insight.auth.models import Role, User, UserStatus
from news_insight.digest.claude import ClaudeError, ClaudeResult
from news_insight.reports import evidence, render, service
from news_insight.reports.models import TrendReport
from news_insight.reports.prompts import PLAN_SCHEMA
from tests.public.seed import NOW, seed_corpus
from tests.public.test_ask_api import fake_embed

pytestmark = pytest.mark.db


def _user(session: Session, username: str = "analyst", role: Role = Role.READER) -> User:
    now = datetime.now(UTC)
    user = User(
        username=username,
        password_hash="x",
        name="분석가" if role == Role.READER else "관리자",
        role=role,
        status=UserStatus.ACTIVE,
        created_at=now,
        password_changed_at=now,
    )
    session.add(user)
    session.flush()
    return user


class FakeClaude:
    """Answers the planner, then writes a report citing the first evidence cards (and one id it
    was never given); records what it was sent."""

    def __init__(self, *, fail_plan: bool = False, fail_write: bool = False) -> None:
        self.fail_plan, self.fail_write = fail_plan, fail_write
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        payload: dict[str, Any],
        *,
        schema: dict[str, Any],
        model: str,
        system: str | None = None,
        instruction: str | None = None,
    ) -> ClaudeResult:
        self.calls.append({"payload": payload, "schema": schema, "system": system})
        if schema is PLAN_SCHEMA:
            if self.fail_plan:
                raise ClaudeError("claude exited 1: usage limit")
            return ClaudeResult(
                structured={
                    "interpretation": "스마트폰의 AI 에이전트 운영체제",
                    "keywords": ["에이전트", "agent OS", "AI"],
                    "companies": ["Samsung Electronics", "없는회사"],
                    "people": [],
                    "queries": ["AI 에이전트가 스마트폰 운영체제가 된다"],
                    "exclude": ["repo"],
                    "questions": {
                        "timeline": ["언제부터?"],
                        "landscape": ["누가?"],
                        "precedents": ["선례?"],
                        "implications": ["DX는?"],
                    },
                },
                cost_usd=0.01,
                model="claude-opus-5-5",
            )
        if self.fail_write:
            raise ClaudeError("claude timed out after 1500s")
        ids = [card["id"] for card in payload["evidence"]]
        return ClaudeResult(
            structured={
                "title": "AI 에이전트 OS 동향",
                "bottom_line": {
                    "judgement": "에이전트 OS가 출시 단계로 넘어갔다",
                    "confidence": "medium",
                    "confidence_reason": "다출처 보도",
                    "item_ids": [ids[0], 999_999_999],
                },
                "key_points": [{"text": "국내 보도가 이어졌다", "item_ids": ids[:2]}],
                "events": [
                    {
                        "date": "2026-10-04",
                        "actor": "Samsung",
                        "action": "출시",
                        "object": "에이전트 OS",
                        "mode": "asserted",
                        "summary": "갤럭시에 탑재",
                        "item_ids": [ids[0]],
                    }
                ],
                "trajectory": {"direction": "accelerating", "points": []},
                "actor_paths": [
                    {
                        "actor": "Samsung",
                        "past": [
                            {"text": "2024년 갤럭시 AI 발표", "basis": "evidence", "item_ids": []},
                        ],
                        "reading": "격상",
                        "next": "확대 적용",
                        "item_ids": [ids[0]],
                    }
                ],
                "actors": [],
                "landscape": [],
                "precedents": [],
                "base_rate": "",
                "implications": [
                    {
                        "area": "모바일",
                        "impact": "opportunity",
                        "first_order": "차별화",
                        "second_order": "앱 생태계",
                        "item_ids": ids[:1],
                    }
                ],
                "assumptions": ["사용자가 에이전트를 받아들인다"],
                "hypotheses": [
                    {
                        "statement": "기본 기능이 된다",
                        "support_ids": ids[:1],
                        "counter_ids": [],
                        "assessment": "반박 근거 없음",
                    }
                ],
                "signposts": [
                    {
                        "indicator": "경쟁사 탑재",
                        "window": "6개월",
                        "likelihood": "높음",
                        "why": "경쟁 압력",
                        "item_ids": [],
                    }
                ],
                "gaps": ["수집 기간이 짧다"],
            },
            cost_usd=0.5,
            model="claude-opus-5-5",
        )


def _queue(session: Session, user: User, topic: str = "AI 에이전트 OS") -> TrendReport:
    return service.request(
        session,
        service.ReportIn(topic=topic, brief="갤럭시 중심으로", days=30),
        user=user,
        now=NOW,
        per_user_daily=5,
        site_daily=20,
    )


def test_writes_a_report_from_the_cards_with_checked_citations(db_session: Session) -> None:
    seed_corpus(db_session)
    embed_cards(db_session, fake_embed, model="bge", now=NOW, limit=100)
    report = _queue(db_session, _user(db_session))
    claude = FakeClaude()

    done = service.run_next(db_session, client=claude, model="opus", embed=fake_embed, now=NOW)

    assert done is not None and done.id == report.id and done.status == "ready", done.error
    sent = claude.calls[1]["payload"]
    titles = [card["title"] for card in sent["evidence"]]
    assert titles and all("repo" not in t for t in titles), "excluded word keeps a card out"
    assert any("에이전트" in t or "agent" in t.lower() for t in titles)
    assert sent["plan"]["companies_not_registered"] == ["없는회사"]
    assert done.plan and "AI 에이전트 OS" in done.plan["keywords"], "the topic always searches"
    # the citation to a card it never saw is gone; an uncited 'evidence' claim is background
    assert 999_999_999 not in done.content["bottom_line"]["item_ids"]
    assert done.content["actor_paths"][0]["past"][0]["basis"] == "background"
    assert done.cost_usd == pytest.approx(0.51)
    html = done.html or ""
    assert html.startswith("<!doctype html>") and "<script" not in html
    assert "핵심 판단" in html and 'href="#ref-1"' in html and 'id="ref-1"' in html
    assert "배경지식·검증 필요" in html and "가속" in html
    doc = render.document(service.report_view(done))
    assert doc.numbers() and doc.sections[0].title == "핵심 판단"


def test_falls_back_to_the_topic_when_planning_fails(db_session: Session) -> None:
    seed_corpus(db_session)
    _queue(db_session, _user(db_session), topic="OLED")
    done = service.run_next(
        db_session, client=FakeClaude(fail_plan=True), model="opus", embed=None, now=NOW
    )
    assert done is not None and done.status == "ready"
    assert done.plan and done.plan["keywords"] == ["OLED"]


def test_failures_are_recorded(db_session: Session) -> None:
    seed_corpus(db_session)
    user = _user(db_session)
    _queue(db_session, user, topic="양자 중력 망원경")
    nothing = service.run_next(
        db_session, client=FakeClaude(fail_plan=True), model="opus", embed=None, now=NOW
    )
    assert nothing is not None and nothing.status == "failed"
    assert nothing.error and "찾지 못했습니다" in nothing.error

    _queue(db_session, user, topic="OLED")
    timed_out = service.run_next(
        db_session, client=FakeClaude(fail_write=True), model="opus", embed=None, now=NOW
    )
    assert timed_out is not None and timed_out.status == "failed"
    assert timed_out.error and "timed out" in timed_out.error
    assert (
        service.run_next(db_session, client=FakeClaude(), model="opus", embed=None, now=NOW) is None
    )


def test_quota_and_queue(db_session: Session) -> None:
    user = _user(db_session)
    _queue(db_session, user)
    _queue(db_session, user, topic="OLED")
    with pytest.raises(service.QuotaExceeded):
        _queue(db_session, user, topic="6G")  # two waiting already
    admin = _user(db_session, "boss", Role.ADMIN)
    for index in range(3):
        _queue(db_session, admin, topic=f"주제 {index}")
    listing = service.summaries(db_session, user=user)
    assert sorted(r.position or 0 for r in listing) == [1, 2, 3, 4, 5]
    with pytest.raises(service.QuotaExceeded):
        service.request(
            db_session,
            service.ReportIn(topic="한도", days=30),
            user=admin,
            now=NOW,
            per_user_daily=5,
            site_daily=5,
        )


def test_plan_cleaning() -> None:
    plan = evidence.plan_from(
        {"keywords": ["a", "월드 모델", "World Model", "world model"], "queries": ["x"]},
        topic="월드 모델",
        brief=None,
    )
    assert plan.keywords == ["월드 모델", "World Model"], "short and repeated words go"
    assert plan.queries == ["월드 모델"]


# --- API --------------------------------------------------------------------------------------


@pytest.fixture
def session_headers(db_session: Session, public_headers: dict[str, str]) -> dict[str, str]:
    issued = accounts.issue_session(
        db_session,
        _user(db_session),
        now=datetime.now(UTC),
        client=Client(ip=None, user_agent=None),
    )
    return {**public_headers, "X-Session-Token": issued.token}


def test_api_request_read_and_export(
    public_client: TestClient, db_session: Session, session_headers: dict[str, str]
) -> None:
    seed_corpus(db_session)
    created = public_client.post(
        "/api/public/reports",
        json={"topic": "  AI   에이전트 OS ", "brief": "갤럭시", "days": 30},
        headers=session_headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["topic"] == "AI 에이전트 OS" and body["status"] == "queued"
    assert body["position"] == 1 and body["mine"] is True and body["can_archive"] is True
    rid = body["id"]
    assert (
        public_client.get(f"/api/public/reports/{rid}/html", headers=session_headers).status_code
        == 409
    )
    bad = public_client.post(
        "/api/public/reports", json={"topic": "x", "days": 7}, headers=session_headers
    )
    assert bad.status_code == 422

    service.run_next(db_session, client=FakeClaude(), model="opus", embed=None, now=NOW)

    page = public_client.get(f"/api/public/reports/{rid}/html", headers=session_headers)
    assert page.status_code == 200 and "script-src" not in page.headers["content-security-policy"]
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert "AI 에이전트 OS 동향" in page.text
    detail = public_client.get(f"/api/public/reports/{rid}", headers=session_headers).json()
    assert detail["status"] == "ready" and detail["evidence"] > 0 and detail["bottom_line"]
    for fmt in ("md", "docx", "pptx", "html"):
        exported = public_client.get(
            f"/api/public/reports/{rid}/export?format={fmt}", headers=session_headers
        )
        assert exported.status_code == 200, fmt
        assert "attachment" in exported.headers["content-disposition"]
    listing = public_client.get("/api/public/reports", headers=session_headers).json()
    assert listing[0]["title"] == "AI 에이전트 OS 동향" and listing[0]["requested_by"] == "분석가"
    assert (
        public_client.delete(f"/api/public/reports/{rid}", headers=session_headers).status_code
        == 204
    )
    assert (
        public_client.get(f"/api/public/reports/{rid}", headers=session_headers).status_code == 404
    )


def test_api_needs_a_session_and_guards_others_reports(
    public_client: TestClient,
    db_session: Session,
    session_headers: dict[str, str],
    public_headers: dict[str, str],
) -> None:
    assert public_client.get("/api/public/reports", headers=public_headers).status_code == 401
    other = _user(db_session, "other")
    report = _queue(db_session, other)
    report.status, report.error = "failed", "x"
    db_session.flush()
    detail = public_client.get(f"/api/public/reports/{report.id}", headers=session_headers).json()
    assert detail["mine"] is False and detail["can_retry"] is False and detail["error"] == "x"
    assert (
        public_client.post(
            f"/api/public/reports/{report.id}/retry", headers=session_headers
        ).status_code
        == 409
    )
    assert (
        public_client.delete(
            f"/api/public/reports/{report.id}", headers=session_headers
        ).status_code
        == 409
    )
