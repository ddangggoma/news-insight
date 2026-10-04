from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.digest.bundle import digest_window
from news_insight.digest.claude import ClaudeError, ClaudeResult
from news_insight.digest.models import DigestStatus
from news_insight.digest.service import digest_out, generate_digest, latest_digest
from tests.factories import build_source

pytestmark = pytest.mark.db
DAY = date(2026, 10, 4)
START, _ = digest_window(DAY)
NOW = datetime(2026, 10, 3, 20, 0, tzinfo=UTC)


class FakeClaude:
    def __init__(self, outcome: dict[str, Any] | ClaudeError) -> None:
        self.outcome = outcome
        self.calls = 0

    def generate(
        self, payload: dict[str, Any], *, schema: dict[str, Any], model: str
    ) -> ClaudeResult:
        self.calls += 1
        if isinstance(self.outcome, ClaudeError):
            raise self.outcome
        return ClaudeResult(structured=self.outcome, cost_usd=0.5, model="claude-opus-x")


def seed(db_session: Session) -> list[int]:
    source = build_source(name="The Verge")
    db_session.add(source)
    db_session.flush()
    ingest_items(
        db_session,
        source,
        [
            RawItem(stable_id="a", url="https://www.example.com/a", title="Galaxy S30"),
            RawItem(stable_id="b", url="https://www.example.com/b", title="OLED 가격"),
        ],
        fetch_run=None,
        now=START + timedelta(hours=2),
        canary=True,
    )
    from sqlalchemy import select

    from news_insight.content.models import Item

    return sorted(db_session.scalars(select(Item.id)))


def claude_output(ids: list[int]) -> dict[str, Any]:
    return {
        "headline": "모바일·디스플레이 동향",
        "overview": "요약",
        "tracks": [
            {
                "track": "news",
                "summary": "뉴스 요약",
                "categories": [
                    {
                        "category": "independent_media",
                        "headline": "주요 보도",
                        "points": [{"text": "출시", "item_ids": [ids[0]]}],
                    }
                ],
            }
        ],
        "insights": [{"title": "가격 압력", "body": "본문", "item_ids": ids}],
    }


def test_published_digest_keeps_evidence_and_item_refs(db_session: Session) -> None:
    ids = seed(db_session)

    digest = generate_digest(
        db_session, digest_date=DAY, now=NOW, client=FakeClaude(claude_output(ids)), model="opus"
    )

    out = digest_out(db_session, digest)
    assert (digest.status, digest.version, digest.item_count, digest.model) == (
        DigestStatus.PUBLISHED,
        1,
        2,
        "claude-opus-x",
    )
    assert {ref.title for ref in out.items} == {"Galaxy S30", "OLED 가격"}
    assert out.content.insights[0].item_ids == ids


def test_claude_failure_publishes_a_fallback(db_session: Session) -> None:
    seed(db_session)

    digest = generate_digest(
        db_session,
        digest_date=DAY,
        now=NOW,
        client=FakeClaude(ClaudeError("timed out")),
        model="opus",
    )

    assert digest.status is DigestStatus.FALLBACK
    assert digest.error == "timed out"
    assert digest.content["tracks"][0]["categories"][0]["points"][0]["text"] in {
        "Galaxy S30",
        "OLED 가격",
    }


def test_same_input_is_not_regenerated(db_session: Session) -> None:
    ids = seed(db_session)
    claude = FakeClaude(claude_output(ids))
    first = generate_digest(db_session, digest_date=DAY, now=NOW, client=claude, model="opus")

    second = generate_digest(db_session, digest_date=DAY, now=NOW, client=claude, model="opus")

    assert second.id == first.id and claude.calls == 1
    assert latest_digest(db_session) is first


def test_empty_day_skips_claude(db_session: Session) -> None:
    claude = FakeClaude(claude_output([1, 2]))

    digest = generate_digest(db_session, digest_date=DAY, now=NOW, client=claude, model="opus")

    assert (digest.status, digest.item_count, claude.calls) == (DigestStatus.FALLBACK, 0, 0)
    assert digest.content["headline"] == "전일 수집된 항목이 없습니다"


def test_radar_signals_reach_the_prompt_and_the_input_hash(db_session: Session) -> None:
    ids = seed(db_session)
    seen: list[dict[str, Any]] = []

    class Capturing(FakeClaude):
        def generate(
            self, payload: dict[str, Any], *, schema: dict[str, Any], model: str
        ) -> ClaudeResult:
            seen.append(payload)
            return super().generate(payload, schema=schema, model=model)

    signals = [{"signal": "급상승", "window": "2026-W40", "topic": "OLED", "detail": "9건"}]
    plain = generate_digest(
        db_session, digest_date=DAY, now=NOW, client=Capturing(claude_output(ids)), model="opus"
    )
    with_signals = generate_digest(
        db_session,
        digest_date=DAY,
        now=NOW,
        client=Capturing(claude_output(ids)),
        model="opus",
        signals=signals,
    )
    assert "radar_signals" not in seen[0]
    assert seen[1]["radar_signals"] == signals
    assert plain.input_hash != with_signals.input_hash
