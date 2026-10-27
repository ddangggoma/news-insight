from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.deals.extract import candidates, scan
from news_insight.deals.models import Deal, DealScan
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


def test_scan_keeps_raises_not_valuations_and_one_stage_spelling(db_session: Session) -> None:
    seed_corpus(db_session, FINANCE)

    def chat(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        assert (
            "valuation"
            in schema["properties"]["results"]["items"]["properties"]["deals"]["items"]["required"]
        )
        import json

        out = []
        for row in json.loads(user):
            deals = []
            if "invests" in row["title"]:
                deals.append(
                    {
                        "kind": "investment",
                        "actor": "Qualcomm Inc.",
                        "counterparty": "EdgeCo",
                        "amount": 5e10,  # 50억 달러 read as 500억
                        "valuation": None,
                        "currency": "USD",
                        "stage": "Series B",
                        "date": "2026-10-03",
                        "summary": "퀄컴이 EdgeCo에 50억 달러를 투자했다.",
                    }
                )
            if "EdgeCo raises" in row["title"]:
                deals.append(
                    {
                        "kind": "investment",
                        "actor": "미공개",
                        "counterparty": "EdgeCo",
                        "amount": 2e10,
                        "valuation": 2e10,
                        "currency": "USD",
                        "stage": "시리즈 B (추정)",
                        "date": "2026-10-03",
                        "summary": "EdgeCo가 투자를 유치했다.",
                    }
                )
            out.append({"id": row["id"], "deals": deals})
        return {"results": out}

    scan(db_session, chat, model="qwen", now=NOW, limit=50)
    named = db_session.scalars(select(Deal).where(Deal.actor != "미공개")).one()
    assert named.actor_key == "qualcomm"  # "Inc." does not hide the registry name
    assert (named.amount, named.amount_usd, named.stage) == (5e9, 5e9, "시리즈 B")
    unnamed = db_session.scalars(select(Deal).where(Deal.actor == "미공개")).one()
    assert (unnamed.amount, unnamed.amount_usd, unnamed.stage) == (None, None, None)


def test_repair_previews_then_cleans_stored_deals(db_session: Session) -> None:
    from typer.testing import CliRunner

    from news_insight import cli
    from news_insight.deals.extract import repair

    ids = seed_corpus(db_session, FINANCE)
    item_id = next(iter(ids.values()))
    common = {"item_id": item_id, "model": "qwen", "extracted_at": NOW, "summary": "x"}
    rows = [
        Deal(kind="ipo", actor="Anthropic", amount=2e12, currency="USD", amount_usd=2e12,
             stage="IPO", **common | {"summary": "기업가치 2조 달러로 IPO를 추진한다."}),
        Deal(kind="investment", actor="Lockheed Martin Canada", counterparty="Qualcomm Inc.",
             amount=11.7e6, currency="CAD", stage="Series A", **common),
    ]  # fmt: skip
    db_session.add_all(rows)
    db_session.flush()

    @contextmanager
    def scope() -> Iterator[Session]:
        with db_session.begin_nested():
            yield db_session

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cli, "session_scope", scope)
        preview = CliRunner().invoke(cli.app, ["cards", "deals-repair"])
        assert preview.exit_code == 0, preview.output
        assert "amounts=2" in preview.output and "preview" in preview.output
        db_session.expire_all()
        assert db_session.get(Deal, rows[0].id).amount == 2e12  # type: ignore[union-attr]
        applied = CliRunner().invoke(cli.app, ["cards", "deals-repair", "--apply"])
        assert applied.exit_code == 0, applied.output
    db_session.expire_all()
    ipo, cad = (db_session.get(Deal, r.id) for r in rows)
    assert ipo is not None and (ipo.amount, ipo.amount_usd) == (None, None)
    assert cad is not None and cad.amount_usd == round(11.7e6 * 0.73)
    assert cad.stage == "시리즈 A" and cad.counterparty_key == "qualcomm"
    again = repair(db_session)
    assert (again.keys, again.stages, again.amounts) == (0, 0, 0)


def test_deals_command_fails_when_no_batch_succeeds(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-17 to 10-27 every night printed failed_batches=6 and exited 0."""
    from typer.testing import CliRunner

    from news_insight import cli
    from news_insight.config import Settings
    from news_insight.deals import extract

    seed_corpus(db_session, FINANCE)

    @contextmanager
    def scope() -> Iterator[Session]:
        with db_session.begin_nested():
            yield db_session

    def down(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("[Errno 61] Connection refused")

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(extract, "lm_studio_chat", lambda url, model: down)
    result = CliRunner().invoke(cli.app, ["cards", "deals"])
    assert result.exit_code == 1
    assert "Connection refused" in result.output


def test_a_dry_run_shows_deals_and_writes_nothing(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from news_insight import cli
    from news_insight.config import Settings
    from news_insight.deals import extract

    seed_corpus(db_session, FINANCE)

    @contextmanager
    def scope() -> Iterator[Session]:
        with db_session.begin_nested():
            yield db_session

    monkeypatch.setattr(cli, "session_scope", scope)
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(extract, "lm_studio_chat", lambda url, model: fake_chat([]))
    result = CliRunner().invoke(cli.app, ["cards", "deals", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "investment Qualcomm → EdgeCo [qualcomm/]" in result.output
    assert db_session.scalars(select(Deal)).all() == []
    assert db_session.scalars(select(DealScan)).all() == []
