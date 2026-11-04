from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item
from news_insight.deals.extract import candidates, scan
from news_insight.deals.models import Deal, DealScan
from news_insight.deals.views import item_day
from tests.public.seed import NOW, Spec, seed_corpus

pytestmark = pytest.mark.db

FINANCE = (
    Spec("Qualcomm invests in edge AI startup", "verge", 5, "ai", ("ai__ai_agents",), "finance"),
    Spec("배터리 합작 법인 설립 MOU", "etnews", 8, "energy", (), "ecosystem"),
    Spec("No money talk here", "verge", 6, "ai", ("ai__ai_agents",), "finance"),
    Spec("EdgeCo raises a Series B round", "etnews", 7, "ai", ("ai__ai_agents",), "finance"),
)


def fake_chat(seen: list[str]) -> Any:
    def chat(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        seen.append(user)
        import json

        rows = json.loads(user)
        results = []
        for row in rows:
            deals = []
            if "invests" in row["title"]:
                deals.append(
                    {
                        "kind": "investment",
                        "actor": "Qualcomm",
                        "counterparty": "EdgeCo",
                        "amount": 50000000,
                        "currency": "usd",
                        "stage": "시리즈 B",
                        "date": "2026-10-03",
                        "summary": "퀄컴이 엣지 AI 스타트업에 투자했다.",
                    }
                )
            if "EdgeCo raises" in row["title"]:  # the same deal, investor not named
                deals.append(
                    {
                        "kind": "investment",
                        "actor": "미상 (투자자 정보 없음)",
                        "counterparty": "EdgeCo",
                        "amount": 51000000,
                        "currency": "USD",
                        "stage": "Series B",
                        "date": "2026-10-03",
                        "summary": "EdgeCo가 시리즈 B를 유치했다.",
                    }
                )
            if "합작" in row["title"]:
                deals.append(
                    {
                        "kind": "joint_venture",
                        "actor": "LG에너지솔루션",
                        "counterparty": None,
                        "amount": 3000000000000,
                        "currency": "KRW",
                        "stage": None,
                        "date": "1999-01-01",
                        "summary": "합작 법인을 세운다.",
                    }
                )
                deals.append(
                    {
                        "kind": "rumor",
                        "actor": "X",
                        "counterparty": None,
                        "amount": None,
                        "currency": None,
                        "stage": None,
                        "date": None,
                        "summary": "x",
                    }
                )
            results.append({"id": row["id"], "deals": deals})
        return {"results": results}

    return chat


def test_scan_reads_hinted_cards_once_and_the_view_sums_them(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    seed_corpus(db_session, FINANCE)
    hinted = {title for _, title, _, _ in candidates(db_session, now=NOW, limit=50)}
    assert any("invests" in t for t in hinted) and not any("No money" in t for t in hinted)

    seen: list[str] = []
    stats = scan(db_session, fake_chat(seen), model="qwen", now=NOW, limit=50)
    assert stats.deals == 2 and stats.read == len(hinted)
    assert scan(db_session, fake_chat(seen), model="qwen", now=NOW, limit=50).read == 0
    undisclosed = db_session.scalars(select(Deal).where(Deal.actor == "미공개")).one()
    assert undisclosed.counterparty == "EdgeCo" and undisclosed.actor_key is None
    deals = {d.kind: d for d in db_session.scalars(select(Deal).where(Deal.actor != "미공개"))}
    assert deals["investment"].currency == "USD" and deals["investment"].amount_usd == 50000000
    # 1999 is background history the article only mentions: dropped
    assert "joint_venture" not in deals
    assert db_session.scalars(select(DealScan)).all()

    body = public_client.get("/api/public/deals", headers=public_headers).json()
    assert body["total"] == 1  # the two reports of the EdgeCo round are one deal
    edge = next(d for d in body["deals"] if d["kind"] == "investment")
    assert edge["reports"] == 2 and edge["actor_key"] == "qualcomm"
    kinds = {k["kind"]: k for k in body["kinds"]}
    assert kinds["investment"]["usd"] == 50000000 and kinds["investment"]["sized"] == 1
    pair = body["pairs"][0]
    assert pair["actor_key"] == "qualcomm" and pair["actor"] == "퀄컴"  # the registry name
    assert pair["counterparty"] == "EdgeCo" and pair["counterparty_key"] is None
    assert body["deals"][0]["title"]
    only = public_client.get(
        "/api/public/deals", params={"kind": "partnership"}, headers=public_headers
    ).json()
    assert only["total"] == 0


def test_a_failed_batch_leaves_cards_for_the_next_run(db_session: Session) -> None:
    seed_corpus(db_session, FINANCE)

    def broken(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("busy")

    stats = scan(db_session, broken, model="qwen", now=NOW, limit=50)
    assert stats.failed_batches == 1 and stats.read == 0
    assert candidates(db_session, now=NOW, limit=50)


def _deal(item_id: int, kind: str, actor: str, counterparty: str | None, **extra: Any) -> Deal:
    return Deal(
        item_id=item_id,
        kind=kind,
        actor=actor,
        actor_key=None,
        counterparty=counterparty,
        counterparty_key=None,
        summary=f"{actor} {kind}",
        model="qwen",
        extracted_at=NOW,
        **extra,
    )


def test_the_view_buckets_deals_by_week_and_month_and_sizes_them(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    seed_corpus(db_session)
    items = {item.title: item for item in db_session.scalars(select(Item))}
    galaxy, oled, repo = (
        items["Galaxy agent OS"],
        items["OLED burn-in compensation"],
        items["oled-compensation repo"],
    )
    db_session.add_all(
        [
            # Thursday 2026-10-01: the week of Monday 09-28
            _deal(
                galaxy.id,
                "investment",
                "Alpha",
                "Beta",
                announced_on=date(2026, 10, 1),
                amount=10e6,
                currency="USD",
                amount_usd=10e6,
            ),
            _deal(
                oled.id,
                "acquisition",
                "Gamma",
                "Delta",
                announced_on=date(2026, 9, 20),
                amount=30e6,
                currency="USD",
                amount_usd=30e6,
            ),
            # no announced date: dated by its article (first seen 2026-10-04 KST)
            _deal(galaxy.id, "partnership", "Alpha", "Epsilon"),
            # a market value read as the amount raised: listed, flagged, never summed
            _deal(
                oled.id,
                "ipo",
                "Omega",
                None,
                announced_on=date(2026, 10, 2),
                amount=2e12,
                currency="USD",
                amount_usd=2e12,
            ),
            # before the 30-day window
            _deal(repo.id, "investment", "Zeta", "Eta", announced_on=date(2026, 8, 1)),
        ]
    )
    db_session.flush()

    body = public_client.get(
        "/api/public/deals", params={"days": 30}, headers=public_headers
    ).json()
    assert body["total"] == 4
    weeks = {w["week"]: w for w in body["weeks"]}
    assert list(weeks) == ["2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28"]
    assert weeks["2026-09-28"]["counts"] == {"investment": 1, "partnership": 1, "ipo": 1}
    assert weeks["2026-09-28"]["usd"] == 10e6
    assert weeks["2026-09-14"]["counts"] == {"acquisition": 1}
    assert weeks["2026-09-07"]["counts"] == {}  # empty weeks are kept, at zero
    months = {m["month"]: m["counts"] for m in body["months"]}
    assert months == {
        "2026-09": {"acquisition": 1},
        "2026-10": {"investment": 1, "partnership": 1, "ipo": 1},
    }
    stats = body["stats"]
    assert stats["sized"] == 2 and stats["usd"] == 40e6
    assert stats["median_usd"] == 20e6 and stats["mean_usd"] == 20e6 and stats["max_usd"] == 30e6
    assert stats["companies"] == 6 and stats["pairs"] == 3 and stats["outliers"] == 1
    assert [p["name"] for p in body["top_usd"]] == ["Gamma", "Delta", "Alpha", "Beta"]
    dated = {d["kind"]: d for d in body["deals"]}
    assert dated["partnership"]["announced_on"] is None
    assert dated["partnership"]["occurred_on"] == "2026-10-04"
    assert dated["investment"]["occurred_on"] == "2026-10-01"
    assert dated["ipo"]["outlier"] and not dated["investment"]["outlier"]
    assert {k["kind"]: k["usd"] for k in body["kinds"]}["ipo"] == 0


def test_an_article_date_later_than_first_seen_is_not_trusted() -> None:
    seen = datetime(2026, 10, 3, 15, 30, tzinfo=UTC)  # 10-04 00:30 KST
    assert item_day(None, seen) == date(2026, 10, 4)
    assert item_day(seen + timedelta(days=30), seen) == date(2026, 10, 4)
    assert item_day(datetime(2026, 9, 30, 1, 0, tzinfo=UTC), seen) == date(2026, 9, 30)
