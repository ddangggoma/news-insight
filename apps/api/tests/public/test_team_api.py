from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.auth import accounts
from news_insight.auth.accounts import Client
from news_insight.auth.models import Role, User, UserStatus
from news_insight.content.models import Item
from tests.public.seed import seed_corpus

pytestmark = pytest.mark.db


def session_headers(
    db_session: Session, public_headers: dict[str, str], username: str
) -> dict[str, str]:
    now = datetime.now(UTC)
    user = User(
        username=username,
        password_hash="x",
        name=username,
        role=Role.READER,
        status=UserStatus.ACTIVE,
        created_at=now,
        password_changed_at=now,
    )
    db_session.add(user)
    db_session.flush()
    token = accounts.issue_session(
        db_session, user, now=now, client=Client(ip=None, user_agent=None)
    ).token
    return {**public_headers, "X-Session-Token": token}


def test_memos_and_collections_are_shared_by_the_team(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    seed_corpus(db_session)
    kim = session_headers(db_session, public_headers, "kim")
    lee = session_headers(db_session, public_headers, "lee")
    card = db_session.scalars(select(Item).where(Item.title == "Galaxy agent OS")).one()
    base = "/api/public/team"

    memo = public_client.post(
        f"{base}/comments",
        json={"kind": "item", "target_id": card.id, "body": "경쟁사 대응 필요"},
        headers=kim,
    )
    assert memo.status_code == 201 and memo.json()[0]["mine"] is True
    seen_by_lee = public_client.get(f"{base}/items/{card.id}", headers=lee).json()
    assert (
        seen_by_lee["comments"][0]["body"] == "경쟁사 대응 필요"
        and seen_by_lee["comments"][0]["mine"] is False
    )
    forbidden = public_client.delete(f"{base}/comments/{memo.json()[0]['id']}", headers=lee)
    assert forbidden.status_code == 403

    created = public_client.post(
        f"{base}/collections", json={"title": "Q4 보고서 근거"}, headers=kim
    ).json()
    cid = created["id"]
    added = public_client.post(
        f"{base}/collections/{cid}/items", json={"item_id": card.id, "note": "표지용"}, headers=lee
    ).json()
    assert (
        added["items"] == 1
        and added["entries"][0]["note"] == "표지용"
        and added["entries"][0]["added_by"] == "lee"
    )
    again = public_client.post(
        f"{base}/collections/{cid}/items", json={"item_id": card.id, "note": "본문"}, headers=kim
    ).json()
    assert again["items"] == 1 and again["entries"][0]["note"] == "본문"
    team = public_client.get(f"{base}/items/{card.id}", headers=kim).json()
    assert [c["id"] for c in team["collections"]] == [cid]
    public_client.post(
        f"{base}/comments",
        json={"kind": "collection", "target_id": cid, "body": "금요일까지"},
        headers=lee,
    )
    assert public_client.get(f"{base}/collections", headers=kim).json()[0]["comments"] == 1
    removed = public_client.delete(f"{base}/collections/{cid}/items/{card.id}", headers=kim).json()
    assert removed["items"] == 0
    assert public_client.delete(f"{base}/collections/{cid}", headers=kim).status_code == 204
    assert public_client.get(f"{base}/collections/{cid}", headers=kim).status_code == 404

    deleted = public_client.delete(f"{base}/comments/{memo.json()[0]['id']}", headers=kim).json()
    assert deleted == []
    assert public_client.get(f"{base}/collections", headers=public_headers).status_code == 401
    missing = public_client.post(
        f"{base}/comments", json={"kind": "dossier", "target_id": 999, "body": "x"}, headers=kim
    )
    assert missing.status_code == 404
