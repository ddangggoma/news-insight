from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item
from news_insight.digest.claude import ClaudeError, ClaudeResult
from news_insight.sources.enums import Track
from news_insight.spotlight import service
from news_insight.spotlight.candidates import SECTIONS, Candidate
from news_insight.spotlight.models import (
    Spotlight,
    SpotlightEntry,
    SpotlightFreeze,
    SpotlightStatus,
)
from news_insight.spotlight.prompts import OUTPUT_SCHEMA, SYSTEM_PROMPT
from news_insight.spotlight.service import build_payload, freeze, listed_counts, validate, write
from tests.factories import build_source

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


def sustained_cand(
    cid: str, section: str, n: int, *, item_ids: list[int] | None = None, **metrics: Any
) -> dict[str, Any]:
    found = cand(f"{cid[0]}{cid[2:]}", section, n, **(metrics or {"days_active": 4}))
    found["cid"] = cid
    found["group"] = "sustained"
    if item_ids is not None:
        found["item_ids"] = item_ids
    return found


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
        "product_name": "",
        "summary": "첫째 문장이다. 둘째 문장이다.",
        "why_hot": "여러 매체가 다뤘다.",
        "rank_note": "",
    } | fields


def output(
    sections: dict[str, Any], sustained: dict[str, list[dict[str, Any]]] | None = None
) -> dict[str, Any]:
    """The writer's answer: a section given as a list is its 24 h group (with the sustained
    group from `sustained`, empty by default); anything else is passed as it is."""
    shaped = {
        section: {"now": listed, "sustained": (sustained or {}).get(section, [])}
        if isinstance(listed, list)
        else listed
        for section, listed in sections.items()
    }
    return {"headline": "오늘의 화제", "benchmark_note": "", "sections": shaped}


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
            .order_by(SpotlightEntry.group != "now", SpotlightEntry.rank)
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
    assert set(payload["sections"]["news"]) == {"now", "sustained"}
    assert payload["sections"]["news"]["sustained"] == []
    assert set(payload["sections"]["news"]["now"][0]) == {
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
    assert [(row.rank, row.title_ko, row.stat_rank) for row in rows[:2]] == [
        (1, "첫째 제목", 1),
        (2, "둘째 제목", 2),
    ]
    assert all(row.fallback is False for row in rows[:2])
    # the places the writer left open are filled from the statistical order
    assert [(row.stat_rank, row.fallback) for row in rows[2:]] == [(i, True) for i in range(3, 13)]
    assert rows[0].key == "item:1"
    assert rows[0].group == "now"
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


def test_now_keeps_ten_beside_five_sustained() -> None:
    found = candidates()
    found["news"] += [sustained_cand(f"ns{i}", "news", 500 + i) for i in range(1, 7)]
    now = [entry([f"n{i}"], i) for i in range(1, 13)]
    later = [entry([f"ns{i}"], i) for i in range(1, 7)]
    kept = validate(output({"news": now}, {"news": later}), found)
    assert [(row["group"], row["rank"]) for row in kept["news"]] == [
        *(("now", i) for i in range(1, 11)),
        *(("sustained", i) for i in range(1, 6)),
    ]
    assert kept["news"][9]["cids"] == ["n10"]
    assert kept["news"][-1]["cids"] == ["ns5"]


def test_a_short_group_lends_its_places_to_the_other() -> None:
    found = candidates()
    found["news"] += [sustained_cand(f"ns{i}", "news", 500 + i) for i in range(1, 15)]
    # two sustained: the 24 h group may take 13
    now = [entry([f"n{i}"], i) for i in range(1, 13)]
    kept = validate(output({"news": now}, {"news": [entry(["ns1"], 1), entry(["ns2"], 2)]}), found)
    assert [row["group"] for row in kept["news"]].count("now") == 12
    assert [row["group"] for row in kept["news"]].count("sustained") == 2
    # three now: the sustained group may take 12
    later = [entry([f"ns{i}"], i) for i in range(1, 15)]
    kept = validate(output({"news": now[:3]}, {"news": later}), found)
    groups = [row["group"] for row in kept["news"]]
    assert (groups.count("now"), groups.count("sustained")) == (3, 12)


def test_a_cid_may_only_be_used_in_its_own_group() -> None:
    found = candidates()
    found["news"] += [sustained_cand("ns1", "news", 501)]
    kept = validate(
        output({"news": [entry(["ns1"], 1), entry(["n1"], 2)]}, {"news": [entry(["n2"], 1)]}),
        found,
    )
    assert [(row["group"], row["cids"]) for row in kept["news"]] == [("now", ["n1"])]


def test_sustained_does_not_repeat_a_24h_pick() -> None:
    found = candidates()
    found["news"] += [
        sustained_cand("ns1", "news", 1),  # the same key as n1
        sustained_cand("ns2", "news", 502, item_ids=[502, 2]),  # shares an item with n2
        sustained_cand("ns3", "news", 503),
    ]
    later = [entry(["ns1"], 1), entry(["ns2"], 2), entry(["ns3"], 3)]
    kept = validate(output({"news": [entry(["n1"], 1), entry(["n2"], 2)]}, {"news": later}), found)
    assert [row["cids"] for row in kept["news"] if row["group"] == "sustained"] == [["ns3"]]
    assert kept["news"][-1]["rank"] == 1


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


def test_missing_section_key_falls_back(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"news": [entry(["n1"], 1)]}))
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
    assert rows[0].tags == []
    assert entries(db_session, result, "news")[0].fallback is False
    assert entries(db_session, result, "patent") == []


def test_non_list_section_falls_back(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"news": [entry(["n1"], 1)], "community": "none"}))  # type: ignore[dict-item]
    result = run(db_session, client)
    assert len(entries(db_session, result, "community")) == 3


def test_empty_section_list_is_respected(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"news": [entry(["n1"], 1)], "community": []}))
    result = run(db_session, client)
    assert result.status is SpotlightStatus.PUBLISHED
    assert entries(db_session, result, "community") == []
    assert entries(db_session, result, "news")[0].fallback is False


def test_all_invalid_items_fall_back(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"community": [entry(["zz9"], 1), entry(["n1"], 2)]}))
    result = run(db_session, client)
    rows = entries(db_session, result, "community")
    assert [(r.stat_rank, r.fallback) for r in rows] == [(1, True), (2, True), (3, True)]


def test_listed_counts_tell_missing_from_empty() -> None:
    raw = output({"news": [entry(["n1"], 1)], "oss": [], "product": "x", "ai": {"now": []}})
    counts = listed_counts(raw)
    assert counts["news"] == {"now": 1, "sustained": 0}
    assert counts["oss"] == {"now": 0, "sustained": 0}
    assert counts["product"] == {"now": None, "sustained": None}
    assert counts["ai"] == {"now": 0, "sustained": None}
    assert counts["patent"] == {"now": None, "sustained": None}


def test_benchmark_note_capped(db_session: Session) -> None:
    seed_freeze(db_session)
    out = output({"news": [entry(["n1"], 1)]}) | {"benchmark_note": "가" * 500}
    result = run(db_session, FakeClaude(out))
    assert len(result.benchmark_note) == 200


def test_product_key_capped_to_column() -> None:
    kept = validate(
        output({"product": [entry(["p1"], 1, product_name="İ" * 80)]}),
        candidates(),
    )
    assert len(kept["product"][0]["key"]) <= 200
    assert len(service._product_key("İ" * 120)) == 200


def test_fallback_takes_the_statistical_order_up_to_fifteen(db_session: Session) -> None:
    seed_freeze(db_session)
    result = run(db_session, FakeClaude(output({})))
    rows = entries(db_session, result, "news")
    # no sustained candidates: the 24 h group takes all twelve
    assert [r.key for r in rows] == [f"item:{i}" for i in range(1, 13)]


def test_fallback_takes_ten_now_and_five_sustained(db_session: Session) -> None:
    found = candidates()
    found["news"] += [sustained_cand(f"ns{i}", "news", 500 + i) for i in range(1, 8)]
    found["news"].append(cand("n13", "news", 13))
    db_session.add(SpotlightFreeze(spotlight_date=DAY, frozen_at=NOW, candidates=found))
    db_session.flush()
    rows = entries(db_session, run(db_session, FakeClaude(ClaudeError("down")), final=True), "news")
    assert [(r.group, r.rank) for r in rows] == [
        *(("now", i) for i in range(1, 11)),
        *(("sustained", i) for i in range(1, 6)),
    ]
    assert all(r.fallback for r in rows)


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
    first, second, *_ = entries(db_session, result, "news")
    assert (first.rank, first.stat_rank, first.rank_note) == (1, 3, "파급이 커서 올림")
    assert (second.rank, second.stat_rank, second.rank_note) == (2, 1, None)


def test_product_group_sums_metrics(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"product": [entry(["p2", "p1"], 1, product_name="Galaxy  S30")]}))
    result = run(db_session, client)
    row, *filled = entries(db_session, result, "product")
    assert [r.fallback for r in filled] == [True]  # p3, the one candidate left
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
    assert entries(db_session, second, "news")[0].key == "item:1"


def test_build_payload_benchmarks_pass_through(db_session: Session) -> None:
    freeze_row = seed_freeze(db_session)
    bench = {"changes": [{"site": "LiveBench", "model": "X", "from": 3, "to": 2}], "new_models": []}
    assert build_payload(freeze_row, {}, bench)["benchmarks"] == bench


def test_write_passes_benchmark_changes_to_payload(db_session: Session) -> None:
    seed_freeze(db_session)
    bench = {
        "changes": [{"site": "LMArena", "model": "X", "from": 3, "to": 2}],
        "new_models": [{"site": "LMArena", "model": "Y", "rank": 5}],
    }
    client = FakeClaude(output({"news": [entry(["n1"], 1)]}))
    write(
        db_session,
        day=DAY,
        now=NOW,
        client=client,
        model=MODEL,
        final_attempt=False,
        benchmarks=bench,
    )
    assert client.calls[0]["payload"]["benchmarks"] == bench


def test_schema_has_no_type_unions() -> None:
    def types(node: Any) -> list[Any]:
        if isinstance(node, dict):
            own = [node["type"]] if "type" in node else []
            return own + [kind for value in node.values() for kind in types(value)]
        if isinstance(node, list):
            return [kind for value in node for kind in types(value)]
        return []

    assert all(isinstance(kind, str) for kind in types(OUTPUT_SCHEMA))


def test_blank_product_name_and_rank_note_become_none(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"product": [entry(["p1"], 1, product_name="", rank_note="")]}))
    row = entries(db_session, run(db_session, client), "product")[0]
    assert row.product_name is None
    assert row.rank_note is None
    assert row.key == "item:101"


def test_long_product_name_dropped_and_day_still_publishes(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(
        output(
            {
                "product": [
                    entry(["p1"], 1, product_name="가" * 200),
                    entry(["p2"], 2, product_name="나" * 80),
                ]
            }
        )
    )
    result = run(db_session, client)
    assert result.status is SpotlightStatus.PUBLISHED
    written = [row for row in entries(db_session, result, "product") if not row.fallback]
    assert [row.product_name for row in written] == ["나" * 80]


def test_cid_repeated_inside_one_entry_counts_once(db_session: Session) -> None:
    seed_freeze(db_session)
    client = FakeClaude(output({"product": [entry(["p1", "p1"], 1, product_name="Galaxy S30")]}))
    row = entries(db_session, run(db_session, client), "product")[0]
    assert row.metrics == {"source_count": 3}
    assert row.item_ids == [101]


def test_oss_topped_up_to_ten_when_opus_lists_fewer(db_session: Session) -> None:
    row = SpotlightFreeze(
        spotlight_date=DAY,
        frozen_at=NOW,
        candidates=candidates() | {"oss": [cand(f"o{i}", "oss", 300 + i) for i in range(1, 13)]},
    )
    db_session.add(row)
    db_session.flush()
    client = FakeClaude(output({"oss": [entry(["o5"], 1), entry(["o2"], 2), entry(["o9"], 3)]}))
    rows = entries(db_session, run(db_session, client), "oss")
    assert [(r.key, r.fallback) for r in rows[:10]] == [
        ("item:305", False),
        ("item:302", False),
        ("item:309", False),
        ("item:301", True),
        ("item:303", True),
        ("item:304", True),
        ("item:306", True),
        ("item:307", True),
        ("item:308", True),
        ("item:310", True),
    ]
    # no sustained candidates: the 24 h group goes on to the last of the twelve
    assert [r.rank for r in rows] == list(range(1, 13))
    assert rows[3].summary == "카드 요약 o1"


def test_oss_filled_to_ten_even_when_the_writer_lists_none(db_session: Session) -> None:
    row = SpotlightFreeze(
        spotlight_date=DAY,
        frozen_at=NOW,
        candidates=candidates() | {"oss": [cand(f"o{i}", "oss", 300 + i) for i in range(1, 13)]},
    )
    db_session.add(row)
    db_session.flush()
    rows = entries(db_session, run(db_session, FakeClaude(output({"oss": []}))), "oss")
    assert len(rows) >= 10
    assert all(r.fallback for r in rows)


def test_oss_filled_as_far_as_its_candidates_go(db_session: Session) -> None:
    row = SpotlightFreeze(
        spotlight_date=DAY,
        frozen_at=NOW,
        candidates=candidates() | {"oss": [cand(f"o{i}", "oss", 300 + i) for i in range(1, 4)]},
    )
    db_session.add(row)
    db_session.flush()
    client = FakeClaude(output({"oss": [entry(["o2"], 1)]}))
    rows = entries(db_session, run(db_session, client), "oss")
    assert [(r.key, r.fallback) for r in rows] == [
        ("item:302", False),
        ("item:301", True),
        ("item:303", True),
    ]


def test_ai_groups_like_product() -> None:
    found = candidates() | {
        "ai": [
            cand("a1", "ai", 401, source_count=3),
            cand("a2", "ai", 402, source_count=2),
            cand("a3", "ai", 403, source_count=2),
        ]
    }
    kept = validate(
        output(
            {
                "ai": [
                    entry(["a2", "a1"], 1, product_name="Gemini 3.8"),
                    entry(["a3"], 2, product_name="가" * 81),
                    entry(["a1", "a3"], 3, product_name="Claude Opus 5.5"),
                ],
                "news": [entry(["n1", "n2"], 1, product_name="Galaxy S30")],
            }
        ),
        found,
    )
    first, second = kept["ai"]
    assert first["key"] == "ai:gemini-3.8"
    assert first["product_name"] == "Gemini 3.8"
    assert first["item_ids"] == [402, 401]
    assert first["metrics"] == {"source_count": 5, "group_size": 2}
    assert first["stat_rank"] == 1
    # the over-long name is dropped; a1 is used, so the third keeps a3 alone
    assert (second["cids"], second["key"], second["rank"]) == (["a3"], "ai:claude-opus-5.5", 2)
    # outside product and ai a group keeps only its first cid and no name
    (news,) = kept["news"]
    assert (news["cids"], news["product_name"], news["key"]) == (["n1"], None, "item:1")


def test_tags_kept_short_distinct_and_at_most_three() -> None:
    tags = ["가격 인하", "  ", "가" * 11, "가격  인하", "첫 공개", 7, "규제 대응", "오픈 웨이트"]
    kept = validate(
        output({"news": [entry(["n1"], 1, tags=tags), entry(["n2"], 2, tags="보안 사고")]}),
        candidates(),
    )
    first, second = kept["news"]
    assert first["tags"] == ["가격 인하", "첫 공개", "규제 대응"]
    assert second["tags"] == []  # not a list: no tags, the entry stays


def test_signals_come_from_the_metrics() -> None:
    assert service.signals("news", {"source_count": 7, "community_mentions": 3}) == [
        "보도 7곳",
        "커뮤니티 확산",
    ]
    assert service.signals("news", {"source_count": 4, "community_mentions": 2}) == []
    assert service.signals("news", {"source_count": 2, "days_active": 4}) == ["7일 중 4일"]
    assert service.signals("oss", {"basis": "github_daily", "trend_rank": 3, "mentions": 5}) == [
        "GitHub 3위"
    ]
    assert service.signals("oss", {"basis": "github_weekly", "trend_rank": 8}) == [
        "GitHub 주간 8위"
    ]
    assert service.signals("oss", {"basis": "github_daily", "best_rank": 2, "days_active": 5}) == [
        "7일 중 5일",
        "GitHub 최고 2위",
    ]
    assert service.signals("oss", {"basis": "hf_trending", "trending": 40}) == ["HF 트렌딩"]
    assert service.signals("ai", {"basis": "benchmark", "rank": 2, "site": "LMArena"}) == [
        "벤치마크 2위"
    ]
    assert service.signals("research", {"mentions": 4, "upvotes": 25}) == [
        "커뮤니티 확산",
        "추천 25",
    ]
    assert service.signals("research", {"upvotes": 19, "flag": True}) == []


def test_tags_signals_group_and_field_are_stored(db_session: Session) -> None:
    src = build_source(key="fieldsrc", name="fieldsrc", operator="x", official_domain="x.com")
    db_session.add(src)
    db_session.flush()
    lead = Item(
        source_id=src.id,
        track=Track.NEWS,
        stable_id="lead",
        url="https://x.com/lead",
        canonical_url="https://x.com/lead",
        title="lead",
        content_hash="h",
        first_seen_at=NOW,
        last_changed_at=NOW,
    )
    db_session.add(lead)
    db_session.flush()
    db_session.add(
        ItemCard(
            item_id=lead.id,
            status=CardStatus.READY,
            title_ko="t",
            input_hash="h",
            generated_at=NOW,
            field="display_av",
        )
    )
    found = candidates()
    found["news"][0]["item_ids"] = [lead.id]
    found["news"][0]["metrics"] = {"source_count": 9, "community_mentions": 4}
    found["ai"] = [
        cand("a1", "ai", 0, basis="benchmark", site="LMArena", board="text", rank=2)
        | {"item_ids": [], "key": "model:x"}
    ]
    found["news"].append(sustained_cand("ns1", "news", 600, days_active=4, source_count=3))
    db_session.add(SpotlightFreeze(spotlight_date=DAY, frozen_at=NOW, candidates=found))
    db_session.flush()
    client = FakeClaude(
        output(
            {"news": [entry(["n1"], 1, tags=["첫 공개"])], "ai": [entry(["a1"], 1)]},
            {"news": [entry(["ns1"], 1, tags=["장기 화제"])]},
        )
    )
    result = run(db_session, client)
    rows = entries(db_session, result, "news")
    first = rows[0]
    assert (first.group, first.tags, first.field) == ("now", ["첫 공개"], "display_av")
    assert first.signals == ["보도 9곳", "커뮤니티 확산"]
    later = [r for r in rows if r.group == "sustained"]
    assert [(r.rank, r.key, r.tags, r.signals) for r in later] == [
        (1, "item:600", ["장기 화제"], ["7일 중 4일"])
    ]
    assert rows[1].field is None  # a lead without a card
    (model,) = entries(db_session, result, "ai")
    assert (model.field, model.signals) == ("ai", ["벤치마크 2위"])


def test_fill_lends_the_short_groups_places_to_the_other(db_session: Session) -> None:
    found = {section: [] for section in SECTIONS} | {
        "news": [cand(f"n{i}", "news", i) for i in range(1, 4)]
        + [sustained_cand(f"ns{i}", "news", 500 + i) for i in range(1, 15)]
    }
    db_session.add(SpotlightFreeze(spotlight_date=DAY, frozen_at=NOW, candidates=found))
    db_session.flush()
    rows = entries(
        db_session, run(db_session, FakeClaude(output({"news": [entry(["n2"], 1)]}))), "news"
    )
    groups = [r.group for r in rows]
    assert (groups.count("now"), groups.count("sustained")) == (3, 12)
    assert [(r.key, r.fallback) for r in rows[:3]] == [
        ("item:2", False),
        ("item:1", True),
        ("item:3", True),
    ]


def test_fill_skips_sustained_candidates_that_repeat_a_24h_entry(db_session: Session) -> None:
    found = {section: [] for section in SECTIONS} | {
        "news": [cand("n1", "news", 1), cand("n2", "news", 2)]
        + [sustained_cand("ns1", "news", 1), sustained_cand("ns2", "news", 502, item_ids=[502, 2])]
        + [sustained_cand("ns3", "news", 503)]
    }
    db_session.add(SpotlightFreeze(spotlight_date=DAY, frozen_at=NOW, candidates=found))
    db_session.flush()
    rows = entries(db_session, run(db_session, FakeClaude(output({}))), "news")
    assert [(r.group, r.key) for r in rows] == [
        ("now", "item:1"),
        ("now", "item:2"),
        ("sustained", "item:503"),
    ]


def test_freeze_stores_both_groups(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service,
        "collect_candidates",
        lambda session, *, day, now: (
            {s: [] for s in SECTIONS} | {"news": [Candidate(**cand("n1", "news", 1))]}
        ),
    )
    monkeypatch.setattr(
        service,
        "collect_sustained",
        lambda session, *, day: (
            {s: [] for s in SECTIONS} | {"news": [Candidate(**sustained_cand("ns1", "news", 9))]}
        ),
    )
    stored = freeze(db_session, day=DAY, now=NOW)
    assert [(c["cid"], c["group"]) for c in stored.candidates["news"]] == [
        ("n1", "now"),
        ("ns1", "sustained"),
    ]
    payload = build_payload(stored, {}, None)
    assert [c["cid"] for c in payload["sections"]["news"]["sustained"]] == ["ns1"]


def test_freeze_survives_a_failed_sustained_collection(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(session: Session, *, day: date) -> dict[str, list[Candidate]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "collect_sustained", broken)
    monkeypatch.setattr(
        service,
        "collect_candidates",
        lambda session, *, day, now: (
            {s: [] for s in SECTIONS} | {"news": [Candidate(**cand("n1", "news", 1))]}
        ),
    )
    stored = freeze(db_session, day=DAY, now=NOW)
    assert [c["cid"] for c in stored.candidates["news"]] == ["n1"]


def test_a_freeze_from_before_the_groups_is_written_as_24h(db_session: Session) -> None:
    old = candidates()
    for found in old.values():
        for candidate in found:
            candidate.pop("group")
    db_session.add(SpotlightFreeze(spotlight_date=DAY, frozen_at=NOW, candidates=old))
    db_session.flush()
    client = FakeClaude(output({"news": [entry(["n1"], 1)]}))
    result = run(db_session, client)
    assert client.calls[0]["payload"]["sections"]["news"]["sustained"] == []
    assert {r.group for r in entries(db_session, result, "news")} == {"now"}


@pytest.mark.parametrize(("listed_now", "listed_sustained"), [(13, 2), (4, 11)])
def test_lent_places_never_take_a_section_past_fifteen(
    db_session: Session, listed_now: int, listed_sustained: int
) -> None:
    found = {section: [] for section in SECTIONS} | {
        "news": [cand(f"n{i}", "news", i) for i in range(1, 16)]
        + [sustained_cand(f"ns{i}", "news", 500 + i) for i in range(1, 16)]
    }
    db_session.add(SpotlightFreeze(spotlight_date=DAY, frozen_at=NOW, candidates=found))
    db_session.flush()
    client = FakeClaude(
        output(
            {"news": [entry([f"n{i}"], i) for i in range(1, listed_now + 1)]},
            {"news": [entry([f"ns{i}"], i) for i in range(1, listed_sustained + 1)]},
        )
    )
    rows = entries(db_session, run(db_session, client), "news")
    groups = [r.group for r in rows]
    assert len(rows) == 15
    assert (groups.count("now"), groups.count("sustained")) == (listed_now, listed_sustained)
    assert not any(r.fallback for r in rows)
