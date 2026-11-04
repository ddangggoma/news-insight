"""The daily 연구 and 특허 insight (insights/writer.py, plan 19 §3): input from the stats with the
reader's gates, the output checks, failed → retried → published, published immutable."""

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.digest.claude import ClaudeError, ClaudeResult
from news_insight.insights.models import DomainInsightRecord, InsightStatus
from news_insight.insights.prompts import OUTPUT_SCHEMA
from news_insight.insights.signals import recompute_signals
from news_insight.insights.writer import (
    NOTE_ENRICHMENT,
    NOTE_SHORT,
    InsightError,
    _numbers,
    build_input,
    validate,
    write,
)
from news_insight.research.models import ResearchDailyStat
from tests.documents import mark_built
from tests.public.test_research_api import at, meta, paper

MODEL = "claude-opus-5-5"
DAY = date(2026, 10, 4)  # the insight's date; the input ends the day before
AS_OF = date(2026, 10, 3)
NOW = at(DAY, 5)  # 05:00 KST


class FakeClaude:
    def __init__(self, outcome: dict[str, Any] | ClaudeError) -> None:
        self.outcome = outcome
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
        self.calls.append({"payload": payload, "schema": schema, "model": model})
        if isinstance(self.outcome, ClaudeError):
            raise self.outcome
        return ClaudeResult(structured=self.outcome, cost_usd=0.75, model=MODEL)


def stat(session: Session, day: date, n: int, *, dim: str = "total", **keys: Any) -> None:
    keys.setdefault("field", "ai")
    session.add(ResearchDailyStat(day=day, dim=dim, n=n, **keys))
    session.flush()


def seed(session: Session, *, history: int | None = 60) -> dict[str, int]:
    """AI papers jump to 12 this week from 3 a week before; two papers with companies. The
    counts were built for the last `history` days (None: the test marks them itself)."""
    if history is not None:
        mark_built(session, AS_OF - timedelta(days=history), AS_OF)
    stat(session, AS_OF, 12)
    stat(session, AS_OF, 2, dim="company", company_key="samsungelectronics")
    stat(session, AS_OF, 1, dim="country", country="KR")
    for back in range(1, 5):
        stat(session, AS_OF - timedelta(days=7 * back), 3)
    own = paper(session, "own", AS_OF - timedelta(days=1))
    meta(session, own, company_keys=["samsungelectronics"])
    peer = paper(session, "peer", AS_OF - timedelta(days=2))
    meta(session, peer, company_keys=["openai"])
    recompute_signals(session, through=AS_OF, now=at(DAY, 4))
    return {"own": own.id, "peer": peer.id}


def output(ids: dict[str, int], **overrides: Any) -> dict[str, Any]:
    body = {
        "overview": [
            {"text": "AI 논문이 12건으로 직전 4주 평균 3건의 4배가 됐다.", "doc_ids": [ids["own"]]},
            {"text": "삼성전자 논문이 2건 나왔다.", "doc_ids": [ids["own"], 999999]},
            {"text": "OpenAI 논문도 이어졌다.", "doc_ids": [ids["peer"]]},
        ],
        "fields": [{"field": "ai", "text": "AI 논문이 크게 늘었다.", "doc_ids": [ids["peer"]]}],
        "companies": [
            {"company_key": "samsungelectronics", "text": "삼성전자 논문 2건.", "doc_ids": []}
        ],
        "watch": "관심 기업 중 삼성전자가 논문을 냈다.",
    }
    return body | overrides


def _types(schema: Any) -> list[Any]:
    found = []
    if isinstance(schema, dict):
        if "type" in schema:
            found.append(schema["type"])
        for key in ("anyOf", "oneOf"):
            assert key not in schema
        for value in schema.values():
            found.extend(_types(value))
    elif isinstance(schema, list):
        for value in schema:
            found.extend(_types(value))
    return found


def test_output_schema_has_no_union_types() -> None:
    assert all(isinstance(t, str) for t in _types(OUTPUT_SCHEMA))
    assert OUTPUT_SCHEMA["required"] == ["overview", "fields", "companies", "watch"]
    field = OUTPUT_SCHEMA["properties"]["fields"]["items"]["properties"]["field"]
    assert len(field["enum"]) == 12 and "ai" in field["enum"]


def test_validate_drops_unknown_ids_fields_companies_long_text_and_invented_numbers() -> None:
    numbers = _numbers({"count": 12, "baseline": 3.0, "ratio": 4.0, "change_pct": 300}, set())
    checked = validate(
        {
            "overview": [
                {"text": "AI 논문 12건, 4.0배, 300% 증가.", "doc_ids": [1, 2, 2, 77, True]},
                {"text": "x" * 201, "doc_ids": [1]},  # too long
                {"text": "AI 논문 99건.", "doc_ids": [1]},  # 99 is not in the input
                {"text": "  ", "doc_ids": [1]},
                {"text": "두 번째 문장.", "doc_ids": "nope"},
                "not an object",
            ],
            "fields": [
                {"field": "ai", "text": "AI 한 줄.", "doc_ids": [2]},
                {"field": "ai", "text": "두 번째 AI 줄.", "doc_ids": []},  # repeated
                {"field": "cooking", "text": "모르는 분야.", "doc_ids": [1]},
                {"field": "semis", "text": "y" * 201, "doc_ids": [1]},
            ],
            "companies": [
                {"company_key": "nobody", "text": "모르는 기업.", "doc_ids": [1]},
                {"company_key": "openai", "text": "OpenAI 한 줄.", "doc_ids": [3]},
            ],
            "watch": "z" * 201,
        },
        doc_ids={1, 2},
        company_keys={"openai"},
        numbers=numbers,
    )
    assert checked["overview"] == [
        {"text": "AI 논문 12건, 4.0배, 300% 증가.", "doc_ids": [1, 2]},
        {"text": "두 번째 문장.", "doc_ids": []},
    ]
    assert checked["fields"] == [{"field": "ai", "text": "AI 한 줄.", "doc_ids": [2]}]
    assert checked["companies"] == [
        {"company_key": "openai", "text": "OpenAI 한 줄.", "doc_ids": []}
    ]
    assert checked["watch"] == ""


def test_validate_needs_two_overview_sentences() -> None:
    with pytest.raises(InsightError):
        validate(
            {"overview": [{"text": "하나뿐.", "doc_ids": []}, {"text": "", "doc_ids": []}]},
            doc_ids=set(),
            company_keys=set(),
            numbers=set(),
        )


@pytest.mark.db
def test_input_holds_the_changes_rising_fields_watched_and_documents(
    db_session: Session,
) -> None:
    ids = seed(db_session)

    payload, doc_ids, companies = build_input(db_session, "research", day=DAY)

    assert payload["as_of"] == "2026-10-03"
    assert payload["window"] == {"start": "2026-09-27", "end": "2026-10-03"}
    assert payload["baseline_window"] == {"start": "2026-08-30", "end": "2026-09-26"}
    ai = next(f for f in payload["fields"] if f["key"] == "ai")
    assert ai == {
        "key": "ai",
        "label": ai["label"],
        "count": 12,
        "baseline": 3.0,
        "change_pct": 300,
        "ratio": 4.0,
    }
    assert [r["key"] for r in payload["rising_fields"]] == ["ai"]
    assert payload["companies"][0]["key"] == "samsungelectronics"
    assert payload["companies"][0]["watched"] is True
    assert [w["key"] for w in payload["watched"]] == ["samsungelectronics"]
    assert [r["key"] for r in payload["regions"]] == ["KR"]
    assert doc_ids == {ids["own"], ids["peer"]}
    doc = next(d for d in payload["documents"] if d["doc_id"] == ids["own"])
    assert doc["field"] == "ai" and doc["title"] == f"카드 {ids['own']}"
    assert doc["companies"] and doc["summary"] == "요약"
    assert "samsungelectronics" in companies
    assert NOTE_SHORT not in payload["coverage_notes"]
    assert any("보강률 100%" in note for note in payload["coverage_notes"])


@pytest.mark.db
def test_input_follows_the_gates_on_short_history_and_thin_enrichment(
    db_session: Session,
) -> None:
    # the four weeks before were built with a tenth of their papers enriched, this week all
    mark_built(
        db_session, AS_OF - timedelta(days=60), AS_OF - timedelta(days=7), research_enriched=10
    )
    mark_built(db_session, AS_OF - timedelta(days=6), AS_OF)
    seed(db_session, history=None)

    payload, _, _ = build_input(db_session, "research", day=DAY)

    assert payload["regions"] == []  # the country axis the reader does not flag either
    assert NOTE_ENRICHMENT in payload["coverage_notes"]
    assert [r["key"] for r in payload["rising_fields"]] == ["ai"]  # fields are not enriched


@pytest.mark.db
def test_short_history_leaves_out_the_rising_fields(db_session: Session) -> None:
    seed(db_session, history=10)

    payload, _, _ = build_input(db_session, "research", day=DAY)

    assert payload["rising_fields"] == []
    assert NOTE_SHORT in payload["coverage_notes"]


@pytest.mark.db
def test_write_publishes_the_validated_insight(db_session: Session) -> None:
    ids = seed(db_session)
    claude = FakeClaude(output(ids))

    row = write(db_session, "research", client=claude, model=MODEL, now=NOW)

    assert row.status is InsightStatus.PUBLISHED and row.insight_date == DAY
    assert row.model == MODEL and row.cost_usd == 0.75 and row.error is None
    assert row.payload["as_of"] == "2026-10-03"
    assert [s["doc_ids"] for s in row.payload["overview"]] == [
        [ids["own"]],
        [ids["own"]],  # the unknown id is gone
        [ids["peer"]],
    ]
    assert row.payload["fields"][0]["field"] == "ai"
    assert row.payload["companies"][0]["company_key"] == "samsungelectronics"
    assert row.payload["watch"].startswith("관심 기업")
    call = claude.calls[0]
    assert call["schema"] is OUTPUT_SCHEMA and call["model"] == MODEL
    assert call["payload"]["kind"] == "research"


@pytest.mark.db
def test_failed_attempt_is_retried_then_published_and_then_immutable(
    db_session: Session,
) -> None:
    ids = seed(db_session)

    failed = write(
        db_session, "research", client=FakeClaude(ClaudeError("usage limit")), model=MODEL, now=NOW
    )
    assert failed.status is InsightStatus.FAILED and failed.error == "usage limit"
    assert failed.payload == {"as_of": "2026-10-03"}

    one_sentence = output(ids, overview=[{"text": "하나.", "doc_ids": []}])
    again = write(db_session, "research", client=FakeClaude(one_sentence), model=MODEL, now=NOW)
    assert again.id == failed.id and again.status is InsightStatus.FAILED
    assert "overview" in (again.error or "")

    published = write(db_session, "research", client=FakeClaude(output(ids)), model=MODEL, now=NOW)
    assert published.id == failed.id and published.status is InsightStatus.PUBLISHED
    assert published.error is None

    later = FakeClaude(output(ids, watch="바뀐 문장."))
    same = write(db_session, "research", client=later, model=MODEL, now=NOW + timedelta(hours=1))
    assert later.calls == []
    assert same.payload["watch"] != "바뀐 문장."
    rows = db_session.scalars(select(DomainInsightRecord)).all()
    assert len(rows) == 1


@pytest.mark.db
def test_nothing_to_write_about_fails_without_calling_claude(db_session: Session) -> None:
    mark_built(db_session, AS_OF - timedelta(days=60), AS_OF)
    claude = FakeClaude(output({"own": 1, "peer": 2}))

    row = write(db_session, "patent", client=claude, model=MODEL, now=NOW)

    assert row.status is InsightStatus.FAILED and "no documents" in (row.error or "")
    assert claude.calls == []


@pytest.mark.db
def test_patent_input_carries_the_coverage_note(db_session: Session) -> None:
    mark_built(db_session, AS_OF - timedelta(days=60), AS_OF)

    payload, doc_ids, _ = build_input(db_session, "patent", day=DAY)

    assert payload["kind"] == "patent" and payload["regions_axis"] == "office"
    assert doc_ids == set()
    assert any("EPO" in note for note in payload["coverage_notes"])
