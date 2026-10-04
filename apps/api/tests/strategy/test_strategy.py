from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.briefing.models import BriefingStatus
from news_insight.briefing.service import failing, publish
from news_insight.content.models import Item
from news_insight.digest.claude import ClaudeError, ClaudeResult
from news_insight.strategy.models import StrategyStatus
from news_insight.strategy.schemas import (
    Review,
    StrategyReport,
    apply_review,
    supported,
    validate_personas,
    validate_report,
)
from news_insight.strategy.service import generate_strategy
from tests.briefing.test_publish import DAY, FREEZE_AT, RULES, FakeClaude, seed

STORY = {1: 10, 2: 10, 3: 30, 4: 40}


def test_evidence_needs_two_distinct_stories() -> None:
    assert supported([1, 2], STORY) == []
    assert supported([1, 3, 99], STORY) == [1, 3]


def test_personas_fill_missing_and_downgrade_unsupported() -> None:
    raw = {
        "personas": [
            {
                "key": "ceo",
                "status": "insight",
                "headline": "h",
                "insight": "i",
                "item_ids": [1, 3],
            },
            {
                "key": "cfo",
                "status": "insight",
                "headline": "h",
                "insight": "i",
                "item_ids": [1, 2],
            },
            {"key": "ghost", "status": "insight", "item_ids": [1, 3]},
        ]
    }

    personas = {p.key: p for p in validate_personas(raw, STORY)}

    assert len(personas) == 30
    assert personas["ceo"].status == "insight" and personas["ceo"].item_ids == [1, 3]
    assert personas["cfo"].status == "no_signal" and personas["mx_head"].status == "no_signal"


def test_report_drops_unsupported_claims_and_reviewer_flags() -> None:
    raw = {
        "summary": "요약",
        "fields": [
            {
                "field": "ai",
                "summary": "s",
                "claims": [
                    {"text": "근거 충분", "item_ids": [1, 3]},
                    {"text": "한 이슈만", "item_ids": [1, 2]},
                ],
            },
            {"field": "memory", "summary": "s", "claims": [{"text": "x", "item_ids": [1, 3]}]},
        ],
        "roadmap": [{"horizon": "3y", "text": "로드맵", "item_ids": [3, 4]}],
        "opportunities": [{"text": "증설 투자 확대", "item_ids": [3, 4]}],
        "risks": [],
    }

    report = validate_report(raw, STORY)
    assert report is not None
    assert [c.id for s in report.fields for c in s.claims] == ["ai-1"]
    assert [s.field for s in report.fields] == ["ai"]

    reviewed, dropped = apply_review(
        report,
        Review(verdict="revise", issues=[{"claim_id": "opp-1", "kind": "semiconductor_asset"}]),
    )
    assert dropped == 1 and reviewed.opportunities == []
    assert isinstance(reviewed, StrategyReport)


class StrategyClaude(FakeClaude):
    def __init__(self, fail_at: str | None = None) -> None:
        self.fail_at = fail_at
        self.instructions: list[str] = []

    def generate(
        self,
        payload: dict[str, Any],
        *,
        schema: dict[str, Any],
        model: str,
        system: str | None = None,
        instruction: str | None = None,
    ) -> ClaudeResult:
        if instruction is None:
            return super().generate(payload, schema=schema, model=model)
        self.instructions.append(instruction)
        ids = [item["id"] for item in payload["items"]]
        if self.fail_at and self.fail_at in instruction:
            raise ClaudeError("boom")
        if "페르소나" in instruction:
            data = {
                "personas": [
                    {
                        "key": "mx_head",
                        "status": "insight",
                        "headline": "h",
                        "insight": "i",
                        "actions": ["a"],
                        "item_ids": ids[:3],
                    }
                ]
            }
        elif "리뷰어" in instruction:
            data = {"verdict": "pass", "issues": []}
        else:
            data = {
                "summary": "요약",
                "fields": [
                    {
                        "field": "ai",
                        "summary": "s",
                        "claims": [
                            {"text": f"주장 {n}", "item_ids": ids[n : n + 3]} for n in range(3)
                        ],
                    }
                ],
                "roadmap": [],
                "opportunities": [],
                "risks": [],
            }
        return ClaudeResult(structured=data, cost_usd=0.2, model="opus")


pytestmark = pytest.mark.db


def test_strategy_run_and_publish_gate(db_session: Session) -> None:
    seed(db_session)
    claude = StrategyClaude()

    briefing = publish(
        db_session, briefing_date=DAY, now=FREEZE_AT, client=claude, model="opus", rules=RULES
    )

    assert briefing.status is BriefingStatus.PUBLISHED, failing(briefing.gates)
    assert {g["name"] for g in briefing.gates} >= {"personas", "strategy"}
    assert len(claude.instructions) == 3
    ids = [i for (i,) in db_session.execute(select(Item.id)).all()]
    again = generate_strategy(
        db_session,
        briefing_date=DAY,
        item_ids=sorted(e["item_id"] for e in briefing.shortlist),
        now=FREEZE_AT,
        client=claude,
        model="opus",
    )
    assert again.id == briefing.strategy_id and len(claude.instructions) == 3 and ids


def test_strategy_failure_blocks_publication(db_session: Session) -> None:
    seed(db_session)

    briefing = publish(
        db_session,
        briefing_date=DAY,
        now=FREEZE_AT + timedelta(minutes=1),
        client=StrategyClaude(fail_at="리뷰어"),
        model="opus",
        rules=RULES,
    )

    assert briefing.status is BriefingStatus.BLOCKED
    assert "전략 주장 출처 2개 이상·리뷰 통과" in failing(briefing.gates)
    from news_insight.strategy.models import StrategyRun

    run = db_session.get(StrategyRun, briefing.strategy_id)
    assert run is not None and run.status is StrategyStatus.FAILED and run.error == "boom"


def test_briefing_api_includes_strategy(
    db_session: Session, console_client: Any, headers: dict[str, str]
) -> None:
    seed(db_session)
    publish(
        db_session,
        briefing_date=DAY,
        now=FREEZE_AT,
        client=StrategyClaude(),
        model="opus",
        rules=RULES,
    )

    body = console_client.get("/api/admin/briefings/latest", headers=headers).json()

    strategy = body["strategy"]
    assert strategy["status"] == "ok" and len(strategy["personas"]) == 30
    mx = next(p for p in strategy["personas"] if p["key"] == "mx_head")
    assert mx["name"] == "MX 사업부장" and mx["status"] == "insight"
    assert strategy["report"]["fields"][0]["claims"][0]["id"] == "ai-1"
    assert {ref["id"] for ref in strategy["items"]} >= set(mx["item_ids"])
