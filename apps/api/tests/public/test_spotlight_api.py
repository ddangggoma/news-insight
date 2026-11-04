from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.spotlight.candidates import SECTIONS
from news_insight.spotlight.models import (
    Spotlight,
    SpotlightEntry,
    SpotlightFreeze,
    SpotlightStatus,
)
from tests.public.seed import NOW, seed_corpus

pytestmark = pytest.mark.db

TODAY = date(2026, 10, 4)  # NOW is 12:00 KST that day
YESTERDAY = TODAY - timedelta(days=1)


def _spotlight(
    session: Session,
    day: date,
    entries: tuple[tuple[str, int, str], ...] = (),
    *,
    status: SpotlightStatus = SpotlightStatus.PUBLISHED,
    item_ids: dict[str, list[int]] | None = None,
) -> Spotlight:
    """`entries` are (section, rank, key) triples."""
    freeze = SpotlightFreeze(spotlight_date=day, frozen_at=NOW, candidates={})
    session.add(freeze)
    session.flush()
    spotlight = Spotlight(
        spotlight_date=day,
        status=status,
        model="claude-opus",
        cost_usd=0.5,
        headline=f"headline {day}",
        benchmark_note=f"note {day}",
        freeze_id=freeze.id,
        generated_at=NOW,
    )
    session.add(spotlight)
    session.flush()
    for section, rank, key in entries:
        session.add(
            SpotlightEntry(
                spotlight_id=spotlight.id,
                section=section,
                rank=rank,
                stat_rank=rank,
                key=key,
                item_ids=(item_ids or {}).get(key, []),
                title_ko=f"title {key}",
                summary="s",
                why_hot="w",
                metrics={"mentions": rank},
            )
        )
    session.flush()
    return spotlight


def _get(client: TestClient, headers: dict[str, str], **params: str) -> dict:
    response = client.get("/api/public/spotlight", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_latest_published_by_default(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    _spotlight(db_session, YESTERDAY - timedelta(days=1), (("news", 1, "old"),))
    _spotlight(db_session, TODAY, (("news", 1, "a"),))
    _spotlight(db_session, YESTERDAY, status=SpotlightStatus.FAILED)
    body = _get(public_client, public_headers)
    assert body["date"] == TODAY.isoformat()
    assert body["generating"] is False
    assert body["headline"] == f"headline {TODAY}"
    assert [e["key"] for e in body["sections"]["news"]] == ["a"]
    assert body["generated_at"] is not None
    # failed rows never show up
    assert body["available_dates"] == [
        TODAY.isoformat(),
        (YESTERDAY - timedelta(days=1)).isoformat(),
    ]


def test_generating_when_today_missing(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    _spotlight(db_session, YESTERDAY, (("news", 1, "a"),))
    _spotlight(db_session, TODAY, status=SpotlightStatus.FAILED)
    body = _get(public_client, public_headers)
    assert body["date"] == YESTERDAY.isoformat()
    assert body["generating"] is True


def test_nothing_published_is_empty_and_generating(
    public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = _get(public_client, public_headers)
    assert body["date"] is None and body["generating"] is True
    assert body["headline"] == "" and body["generated_at"] is None
    assert body["available_dates"] == []
    assert set(body["sections"]) == set(SECTIONS)


def test_explicit_older_date_is_not_generating(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    _spotlight(db_session, YESTERDAY, (("news", 1, "a"),))
    _spotlight(db_session, TODAY, (("news", 1, "a"),))
    body = _get(public_client, public_headers, date=YESTERDAY.isoformat())
    assert body["date"] == YESTERDAY.isoformat()
    assert body["generating"] is False
    assert body["available_dates"][0] == TODAY.isoformat()


def test_change_new_up_down(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    _spotlight(db_session, YESTERDAY, (("news", 3, "A"), ("news", 1, "B"), ("product", 1, "C")))
    _spotlight(
        db_session,
        TODAY,
        (("news", 1, "A"), ("news", 2, "B"), ("news", 3, "C"), ("product", 1, "C")),
    )
    news = {e["key"]: e for e in _get(public_client, public_headers)["sections"]["news"]}
    assert (news["A"]["change"], news["A"]["change_by"]) == ("up", 2)
    assert (news["B"]["change"], news["B"]["change_by"]) == ("down", 1)
    # C was in another section yesterday: compared by (section, key), so it is new here
    assert (news["C"]["change"], news["C"]["change_by"]) == ("new", 0)
    product = _get(public_client, public_headers)["sections"]["product"]
    assert (product[0]["change"], product[0]["change_by"]) == ("same", 0)


def test_no_previous_day_all_new(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    # two days back does not count: only the immediately preceding calendar day does
    _spotlight(db_session, TODAY - timedelta(days=2), (("news", 1, "A"),))
    _spotlight(db_session, TODAY, (("news", 1, "A"),))
    entry = _get(public_client, public_headers)["sections"]["news"][0]
    assert (entry["change"], entry["change_by"]) == ("new", 0)


def test_previous_failed_day_does_not_count(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    _spotlight(db_session, YESTERDAY, (("news", 2, "A"),), status=SpotlightStatus.FAILED)
    _spotlight(db_session, TODAY, (("news", 1, "A"),))
    assert _get(public_client, public_headers)["sections"]["news"][0]["change"] == "new"


def test_unknown_date_404(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    _spotlight(db_session, YESTERDAY, status=SpotlightStatus.FAILED)
    for day in (YESTERDAY, TODAY - timedelta(days=30)):
        response = public_client.get(
            "/api/public/spotlight", params={"date": day.isoformat()}, headers=public_headers
        )
        assert response.status_code == 404


def test_sections_include_all_keys(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    _spotlight(db_session, TODAY, (("news", 2, "b"), ("news", 1, "a")))
    sections = _get(public_client, public_headers)["sections"]
    assert set(sections) == set(SECTIONS)
    assert [e["key"] for e in sections["news"]] == ["a", "b"]  # by rank
    assert sections["patent"] == []


def test_entry_fields_and_url_of_representative_item(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    ids = seed_corpus(db_session)
    first, second = sorted(ids.values())[:2]
    _spotlight(
        db_session,
        TODAY,
        (("news", 1, "with-url"), ("news", 2, "no-items"), ("news", 3, "gone")),
        item_ids={"with-url": [second, first], "gone": [999_999]},
    )
    news = {e["key"]: e for e in _get(public_client, public_headers)["sections"]["news"]}
    assert news["with-url"]["url"].startswith("https://")
    assert news["with-url"]["item_ids"] == [second, first]
    assert news["no-items"]["url"] is None and news["gone"]["url"] is None
    entry = news["with-url"]
    assert entry["rank"] == 1 and entry["stat_rank"] == 1 and entry["fallback"] is False
    assert entry["metrics"] == {"mentions": 1} and entry["product_name"] is None
    assert entry["title_ko"] == "title with-url" and entry["rank_note"] is None
    assert {"summary", "why_hot"} <= set(entry)


def test_available_dates_capped_at_sixty(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    for back in range(65):
        _spotlight(db_session, TODAY - timedelta(days=back))
    dates = _get(public_client, public_headers)["available_dates"]
    assert len(dates) == 60 and dates[0] == TODAY.isoformat()


def test_requires_public_key(public_client: TestClient) -> None:
    assert public_client.get("/api/public/spotlight").status_code in (401, 403)


def test_groups_tags_signals_and_field(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    spotlight = _spotlight(db_session, YESTERDAY, (("news", 1, "kept"),))
    today = _spotlight(db_session, TODAY, (("news", 2, "b"), ("news", 1, "a")))
    for rank, key in ((2, "late"), (1, "kept")):
        db_session.add(
            SpotlightEntry(
                spotlight_id=today.id,
                section="news",
                rank=rank,
                stat_rank=rank,
                key=key,
                item_ids=[],
                title_ko=f"title {key}",
                summary="s",
                why_hot="w",
                metrics={"days_active": 4},
                group="sustained",
                tags=["장기 화제"],
                signals=["7일 중 4일"],
                field="ai",
            )
        )
    db_session.flush()
    assert spotlight.id != today.id
    news = _get(public_client, public_headers)["sections"]["news"]
    # the 24 h entries by rank, then the sustained ones by rank
    assert [(e["group"], e["rank"], e["key"]) for e in news] == [
        ("now", 1, "a"),
        ("now", 2, "b"),
        ("sustained", 1, "kept"),
        ("sustained", 2, "late"),
    ]
    kept = news[2]
    assert kept["tags"] == ["장기 화제"] and kept["signals"] == ["7일 중 4일"]
    assert kept["field"] == "ai" and kept["field_label"] == "AI 모델·에이전트"
    # the change is by section and key, whatever the group
    assert (kept["change"], news[3]["change"]) == ("same", "new")
    # entries published before the groups: 24 h, no tags, signals or field
    assert (news[0]["tags"], news[0]["signals"], news[0]["field"], news[0]["field_label"]) == (
        [],
        [],
        None,
        None,
    )
