from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.digest.claude import ClaudeError, ClaudeResult
from news_insight.spotlight import service
from news_insight.spotlight.candidates import SECTIONS, Candidate
from news_insight.spotlight.models import (
    Spotlight,
    SpotlightEntry,
    SpotlightFreeze,
    SpotlightStatus,
)
from news_insight.spotlight.prompts import OUTPUT_SCHEMA, SYSTEM_PROMPT
from news_insight.spotlight.service import build_payload, freeze, validate, write

pytestmark = pytest.mark.db
DAY = date(2026, 11, 4)
NOW = datetime(2026, 11, 3, 20, 0, tzinfo=UTC)
MODEL = "claude-opus-5-5"


def cand(cid: str, section: str, n: int, **metrics: Any) -> dict[str, Any]:
    return Candidate(
        cid=cid,
        section=section,
        key=f"item:{n}",
        item_ids=[n],
        title_ko=f"제목 {cid}",
        summary_ko=f"카드 요약 {cid}",
        url=f"https://example.com/{n}",
        metrics=metrics or {"source_count": 1},
        score=100.0 - n,
        stat_rank=int(cid[1:]),
    ).to_json()


def candidates() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {section: [] for section in SECTIONS}
    out["news"] = [cand(f"n{i}", "news", i, source_count=20 - i) for i in range(1, 13)]
    out["product"] = [
        cand("p1", "product", 101, source_count=3),
        cand("p2", "product", 102, source_count=2),
        cand("p3", "product", 103, source_count=1),
    ]
    out["community"] = [cand(f"c{i}", "community", 200 + i) for i in range(1, 4)]
    return out


def entry(cids: list[str], rank: int, **fields: Any) -> dict[str, Any]:
    return {
        "cids": cids,
        "rank": rank,
        "title_ko": f"다듬은 제목 {cids[0]}",
        "product_name": None,
        "summary": "첫째 문장이다. 둘째 문장이다.",
        "why_hot": "여러 매체가 다뤘다.",
        "rank_note": None,
    } | fields


def output(sections: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {"headline": "오늘의 화제", "benchmark_note": "", "sections": sections}


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
        self.calls.append(
            {
                "payload": payload,
                "schema": schema,
                "model": model,
                "system": system,
                "instruction": instruction,
            }
        )
        if isinstance(self.outcome, ClaudeError):
            raise self.outcome
        return ClaudeResult(structured=self.outcome, cost_usd=1.25, model=MODEL)


def seed_freeze(session: Session) -> SpotlightFreeze:
    row = SpotlightFreeze(spotlight_date=DAY, frozen_at=NOW, candidates=candidates())
    session.add(row)
    session.flush()
    return row


def run(session: Session, client: FakeClaude, *, final: bool = False) -> Spotlight:
    return write(session, day=DAY, now=NOW, client=client, model=MODEL, final_attempt=final)


def entries(session: Session, spotlight: Spotlight, section: str) -> list[SpotlightEntry]:
    return list(
        session.scalars(
            select(SpotlightEntry)
            .where(SpotlightEntry.spotlight_id == spotlight.id, SpotlightEntry.section == section)
            .order_by(SpotlightEntry.rank)
        )
    )


def test_freeze_is_idempotent(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_collect(session: Session, *, day: date, now: datetime) -> dict[str, list[Candidate]]:
        calls.append(day)
        return {section: [] for section in SECTIONS} | {
            "news": [Candidate(**cand("n1", "news", 1))]
        }

    monkeypatch.setattr(service, "collect_candidates", fake_collect)
    first = freeze(db_session, day=DAY, now=NOW)
    second = freeze(db_session, day=DAY, now=NOW + timedelta(hours=1))
    assert first.id == second.id
    assert calls == [DAY]
    assert first.frozen_at == NOW
    assert set(first.candidates) == set(SECTIONS)
    assert first.candidates["news"][0]["cid"] == "n1"
    assert first.candidates["news"][0]["metrics"] == {"source_count": 1}


def test_write_freezes_when_missing(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service,
        "collect_candidates",
        lambda session, *, day, now: {section: [] for section in SECTIONS},
    )
    client = FakeClaude(output({}))
    result = run(db_session, client)
    stored = db_session.scalars(select(SpotlightFreeze)).one()
    assert result.freeze_id == stored.id
    assert result.status is SpotlightStatus.PUBLISHED


def test_payload_and_call_shape(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"news": [entry(["n1"], 1)]}))
    run(db_session, client)
    call = client.calls[0]
    assert call["model"] == MODEL
    assert call["schema"] is OUTPUT_SCHEMA
    assert call["system"] == SYSTEM_PROMPT
    payload = call["payload"]
    assert payload["date"] == "2026-11-04"
    assert payload["previous"] == {}
    assert payload["benchmarks"] == {"changes": [], "new_models": []}
    assert set(payload["sections"]) == set(SECTIONS)
    assert set(payload["sections"]["news"][0]) == {
        "cid",
        "title_ko",
        "summary_ko",
        "metrics",
        "stat_rank",
    }


def test_previous_is_yesterdays_published_titles(db_session: Session) -> None:
    old = SpotlightFreeze(spotlight_date=DAY - timedelta(days=1), frozen_at=NOW, candidates={})
    db_session.add(old)
    db_session.flush()
    day_before = Spotlight(
        spotlight_date=DAY - timedelta(days=1),
        status=SpotlightStatus.PUBLISHED,
        model=MODEL,
        cost_usd=1.0,
        headline="",
        benchmark_note="",
        freeze_id=old.id,
        error=None,
        generated_at=NOW,
    )
    db_session.add(day_before)
    db_session.flush()
    for rank, title in ((2, "둘째"), (1, "첫째")):
        db_session.add(
            SpotlightEntry(
                spotlight_id=day_before.id,
                section="news",
                rank=rank,
                stat_rank=rank,
                key=f"item:{rank}",
                item_ids=[rank],
                title_ko=title,
                summary="",
                why_hot="",
                metrics={},
                fallback=False,
            )
        )
    db_session.flush()
    seed_freeze(db_session)
    client = FakeClaude(output({}))
    run(db_session, client)
    assert client.calls[0]["payload"]["previous"] == {"news": ["첫째", "둘째"]}


def test_valid_output_published(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(
        output(
            {
                "news": [
                    entry(["n2"], 2, title_ko="둘째 제목"),
                    entry(["n1"], 1, title_ko="첫째 제목"),
                ]
            }
        )
    )
    result = run(db_session, client)
    assert result.status is SpotlightStatus.PUBLISHED
    assert result.model == "claude-opus-5-5"
    assert result.cost_usd == 1.25
    assert result.headline == "오늘의 화제"
    assert result.error is None
    rows = entries(db_session, result, "news")
    assert [(row.rank, row.title_ko, row.stat_rank) for row in rows] == [
        (1, "첫째 제목", 1),
        (2, "둘째 제목", 2),
    ]
    assert all(row.fallback is False for row in rows)
    assert rows[0].key == "item:1"
    assert rows[0].item_ids == [1]
    assert rows[0].summary == "첫째 문장이다. 둘째 문장이다."
    assert rows[0].metrics == {"source_count": 19}


def test_unknown_cid_dropped() -> None:
    kept = validate(output({"news": [entry(["zz9"], 1), entry(["n1"], 2)]}), candidates())
    assert [row["cids"] for row in kept["news"]] == [["n1"]]
    assert kept["news"][0]["rank"] == 1


def test_cross_section_cid_dropped() -> None:
    kept = validate(output({"news": [entry(["p1"], 1), entry(["n1"], 2)]}), candidates())
    assert [row["cids"] for row in kept["news"]] == [["n1"]]


def test_unknown_section_ignored() -> None:
    kept = validate(output({"weather": [entry(["n1"], 1)]}), candidates())
    assert "weather" not in kept
    assert kept["news"] == []


def test_cid_used_twice_kept_once() -> None:
    kept = validate(
        output(
            {
                "product": [
                    entry(["p1", "p2"], 1, product_name="Galaxy S30"),
                    entry(["p1", "p3"], 2, product_name="Pixel 12"),
                    entry(["p1"], 3, product_name="Nothing Phone"),
                ]
            }
        ),
        candidates(),
    )
    assert [row["cids"] for row in kept["product"]] == [["p1", "p2"], ["p3"]]


def test_more_than_ten_truncated() -> None:
    entries_ = [entry([f"n{i}"], i) for i in range(1, 13)]
    kept = validate(output({"news": entries_}), candidates())
    assert [row["rank"] for row in kept["news"]] == list(range(1, 11))
    assert kept["news"][-1]["cids"] == ["n10"]


def test_overlong_fields_dropped() -> None:
    kept = validate(
        output(
            {
                "news": [
                    entry(["n1"], 1, summary="가" * 261),
                    entry(["n2"], 2, why_hot="가" * 141),
                    entry(["n3"], 3, title_ko="가" * 121),
                    entry(["n4"], 4, rank_note="가" * 141),
                    entry(["n5"], 5, summary="가" * 260, why_hot="가" * 140, title_ko="가" * 120),
                ]
            }
        ),
        candidates(),
    )
    assert [row["cids"] for row in kept["news"]] == [["n5"]]
    assert kept["news"][0]["rank"] == 1


def test_missing_title_uses_candidate_title() -> None:
    kept = validate(output({"news": [entry(["n1"], 1, title_ko="  ")]}), candidates())
    assert kept["news"][0]["title_ko"] == "제목 n1"


def test_empty_section_falls_back(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"news": [entry(["n1"], 1)], "community": []}))
    result = run(db_session, client)
    rows = entries(db_session, result, "community")
    assert [(r.rank, r.stat_rank, r.fallback) for r in rows] == [
        (1, 1, True),
        (2, 2, True),
        (3, 3, True),
    ]
    assert rows[0].summary == "카드 요약 c1"
    assert rows[0].why_hot == ""
    assert rows[0].title_ko == "제목 c1"
    assert entries(db_session, result, "news")[0].fallback is False
    assert entries(db_session, result, "patent") == []


def test_fallback_takes_top_ten_by_stat_rank(db_session: Session) -> None:
    seed_freeze(db_session)
    result = run(db_session, FakeClaude(output({})))
    rows = entries(db_session, result, "news")
    assert [r.key for r in rows] == [f"item:{i}" for i in range(1, 11)]


def test_rank_note_kept_and_stat_rank_stored(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(
        output(
            {
                "news": [
                    entry(["n3"], 1, rank_note="파급이 커서 올림"),
                    entry(["n1"], 2, rank_note="   "),
                ]
            }
        )
    )
    result = run(db_session, client)
    first, second = entries(db_session, result, "news")
    assert (first.rank, first.stat_rank, first.rank_note) == (1, 3, "파급이 커서 올림")
    assert (second.rank, second.stat_rank, second.rank_note) == (2, 1, None)


def test_product_group_sums_metrics(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"product": [entry(["p2", "p1"], 1, product_name="Galaxy  S30")]}))
    result = run(db_session, client)
    (row,) = entries(db_session, result, "product")
    assert row.metrics == {"source_count": 5, "group_size": 2}
    assert sorted(row.item_ids) == [101, 102]
    assert row.key == "product:galaxy-s30"
    assert row.product_name == "Galaxy  S30"
    assert row.stat_rank == 1


def test_claude_error_not_final_records_failed(db_session: Session) -> None:
    seed_freeze(db_session)
    with pytest.raises(ClaudeError):
        run(db_session, FakeClaude(ClaudeError("claude exited 1: Not logged in")))
    row = db_session.scalars(select(Spotlight)).one()
    assert row.status is SpotlightStatus.FAILED
    assert row.error is not None and "Not logged in" in row.error
    assert db_session.scalars(select(SpotlightEntry)).all() == []


def test_failed_row_is_updated_in_place_by_a_later_success(db_session: Session) -> None:
    seed_freeze(db_session)
    with pytest.raises(ClaudeError):
        run(db_session, FakeClaude(ClaudeError("boom")))
    failed = db_session.scalars(select(Spotlight)).one()
    result = run(db_session, FakeClaude(output({"news": [entry(["n1"], 1)]})))
    assert result.id == failed.id
    assert result.status is SpotlightStatus.PUBLISHED
    assert result.error is None
    assert len(db_session.scalars(select(Spotlight)).all()) == 1


def test_malformed_response_counts_as_failure(db_session: Session) -> None:
    seed_freeze(db_session)
    with pytest.raises(ClaudeError):
        run(db_session, FakeClaude({"headline": "x", "benchmark_note": "", "sections": []}))
    assert db_session.scalars(select(Spotlight)).one().status is SpotlightStatus.FAILED


def test_claude_error_final_publishes_fallback(db_session: Session) -> None:
    seed_freeze(db_session)
    result = run(db_session, FakeClaude(ClaudeError("down")), final=True)
    assert result.status is SpotlightStatus.PUBLISHED
    assert result.error is not None and "down" in result.error
    assert result.cost_usd is None
    stored = list(db_session.scalars(select(SpotlightEntry)))
    assert {row.section for row in stored} == {"news", "product", "community"}
    assert all(row.fallback is True for row in stored)


def test_published_is_immutable(db_session: Session) -> None:
    seed_freeze(db_session)
    first = run(db_session, FakeClaude(output({"news": [entry(["n1"], 1)]})))
    second_client = FakeClaude(output({"news": [entry(["n2"], 1)]}))
    second = run(db_session, second_client, final=True)
    assert second.id == first.id
    assert second_client.calls == []
    assert [row.key for row in entries(db_session, second, "news")] == ["item:1"]


def test_build_payload_benchmarks_pass_through(db_session: Session) -> None:
    freeze_row = seed_freeze(db_session)
    bench = {"changes": [{"site": "LiveBench", "model": "X", "from": 3, "to": 2}], "new_models": []}
    assert build_payload(freeze_row, {}, bench)["benchmarks"] == bench
