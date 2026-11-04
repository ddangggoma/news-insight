from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import (
    AiModel,
    AiModelAlias,
    BenchmarkScore,
    BenchmarkSnapshot,
)

pytestmark = pytest.mark.db

SEEN = datetime(2026, 11, 3, 3, 30, tzinfo=UTC)


def snap(session: Session, site: str, when: datetime = SEEN, sha: str = "x") -> BenchmarkSnapshot:
    row = BenchmarkSnapshot(site=site, release="r", fetched_at=when, sha256=f"{site}{sha}", raw={})
    session.add(row)
    session.flush()
    return row


def score(
    session: Session,
    snapshot: BenchmarkSnapshot,
    raw: str,
    *,
    org: str | None = None,
    model_id: int | None = None,
    metric: str = "rating",
) -> BenchmarkScore:
    row = BenchmarkScore(
        snapshot_id=snapshot.id,
        site=snapshot.site,
        board="b",
        model_raw=raw,
        model_id=model_id,
        org=org,
        metric=metric,
        value=1.0,
        extra={},
    )
    session.add(row)
    session.flush()
    return row


def test_unmatched_lists_null_model_names(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    known = AiModel(name="known")
    db_session.add(known)
    db_session.flush()
    lm = snap(db_session, "lmarena")
    lb = snap(db_session, "livebench", datetime(2026, 11, 2, tzinfo=UTC))
    score(db_session, lm, "Mystery (High)", org="Acme")
    score(db_session, lm, "Mystery (High)", metric="other")
    score(db_session, lb, "Mystery (High)")
    score(db_session, lb, "Solo")
    score(db_session, lm, "known", model_id=known.id)

    body = console_client.get("/api/admin/benchmarks/unmatched", headers=headers).json()

    assert [r["model_raw"] for r in body] == ["Mystery (High)", "Solo"]
    mystery = body[0]
    assert mystery["org"] == "Acme"
    assert mystery["sites"] == ["livebench", "lmarena"]
    assert mystery["last_seen"].startswith("2026-11-03T03:30")
    assert body[1]["sites"] == ["livebench"] and body[1]["org"] is None


def test_unmatched_only_reads_each_sites_latest_snapshot(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    old = snap(db_session, "lmarena", datetime(2026, 10, 1, tzinfo=UTC), "old")
    new = snap(db_session, "lmarena", SEEN, "new")
    score(db_session, old, "Gone")
    score(db_session, new, "Here")
    body = console_client.get("/api/admin/benchmarks/unmatched", headers=headers).json()
    assert [r["model_raw"] for r in body] == ["Here"]


def test_alias_backfills_existing_scores(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    old = snap(db_session, "lmarena", datetime(2026, 10, 1, tzinfo=UTC), "old")
    new = snap(db_session, "lmarena", SEEN, "new")
    exact = score(db_session, new, "Claude Opus 5 (High)")
    spelling = score(db_session, new, "claude-opus-5")  # same name once normalized
    older = score(db_session, old, "Claude Opus 5 (Low)")
    other = score(db_session, new, "Something else")

    response = console_client.post(
        "/api/admin/benchmarks/aliases",
        headers=headers,
        json={"alias": "Claude Opus 5 (High)", "model_name": "Claude Opus 5", "org": "Anthropic"},
    )

    assert response.status_code == 201, response.text
    model = db_session.scalars(select(AiModel)).one()
    assert (model.name, model.org) == ("claude-opus-5", "Anthropic")
    assert response.json() == {"model_id": model.id, "model": "claude-opus-5", "linked": 3}
    for row in (exact, spelling, older, other):
        db_session.refresh(row)
    assert (exact.model_id, spelling.model_id, older.model_id) == (model.id,) * 3
    assert other.model_id is None
    alias = db_session.scalars(select(AiModelAlias)).one()
    assert (alias.alias, alias.model_id) == ("Claude Opus 5 (High)", model.id)
    # and the name is no longer listed
    listed = console_client.get("/api/admin/benchmarks/unmatched", headers=headers).json()
    assert [r["model_raw"] for r in listed] == ["Something else"]


def test_alias_reuses_an_existing_model(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    model = AiModel(name="gem", org=None)
    db_session.add(model)
    db_session.flush()
    row = score(db_session, snap(db_session, "lmarena"), "GEM-pro")

    response = console_client.post(
        "/api/admin/benchmarks/aliases",
        headers=headers,
        json={"alias": "GEM-pro", "model_name": "Gem", "org": "Google"},
    )

    assert response.status_code == 201
    assert db_session.scalars(select(AiModel)).one().org == "Google"  # a missing org is filled
    db_session.refresh(row)
    assert row.model_id == model.id


def test_alias_keeps_an_existing_org(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    db_session.add(AiModel(name="gem", org="Google"))
    db_session.flush()
    console_client.post(
        "/api/admin/benchmarks/aliases",
        headers=headers,
        json={"alias": "g", "model_name": "gem", "org": "Other"},
    )
    assert db_session.scalars(select(AiModel)).one().org == "Google"


def test_alias_to_another_model_conflicts(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    first = AiModel(name="one")
    db_session.add(first)
    db_session.flush()
    db_session.add(AiModelAlias(alias="x", model_id=first.id))
    db_session.flush()

    again = console_client.post(
        "/api/admin/benchmarks/aliases", headers=headers, json={"alias": "x", "model_name": "one"}
    )
    clash = console_client.post(
        "/api/admin/benchmarks/aliases", headers=headers, json={"alias": "x", "model_name": "two"}
    )

    assert again.status_code == 201  # the same link twice is fine
    assert clash.status_code == 409
    assert db_session.scalars(select(AiModel).where(AiModel.name == "two")).first() is None


@pytest.mark.parametrize(
    "body",
    [
        {"alias": "x", "model_name": "m" * 121},
        {"alias": "x", "model_name": "  "},
        {"alias": "x", "model_name": "(High)"},  # nothing left once normalized
        {"alias": "", "model_name": "m"},
        {"alias": "a" * 201, "model_name": "m"},
        {"alias": "x", "model_name": "m", "org": "o" * 81},
    ],
)
def test_alias_rejects_bad_input(
    console_client: TestClient, headers: dict[str, str], body: dict[str, str]
) -> None:
    response = console_client.post("/api/admin/benchmarks/aliases", headers=headers, json=body)
    assert response.status_code == 422


def test_benchmark_console_needs_the_key(console_client: TestClient) -> None:
    assert console_client.get("/api/admin/benchmarks/unmatched").status_code == 401
