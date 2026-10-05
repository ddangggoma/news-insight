from collections import Counter
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.public.companies import activity_shift, has_history, theme_leaders
from news_insight.sources.enums import Region
from news_insight.taxonomy.catalog import TAXONOMY_REVISION
from tests.factories import build_source
from tests.public.seed import NOW

_serial = iter(range(100_000))


def test_activity_shift_needs_a_significant_and_large_move() -> None:
    shift = activity_shift(Counter(launch=8, research=1), Counter(research=10, launch=1))
    assert shift is not None and shift.signal_type == "launch"
    assert shift.share == pytest.approx(0.889, abs=0.001) and shift.z >= 2
    assert activity_shift(Counter(launch=3), Counter(research=10)) is None  # too few now
    assert activity_shift(Counter(launch=6, research=5), Counter(launch=5, research=5)) is None


def test_new_and_first_need_earlier_windows_with_reports() -> None:
    # 2026-10-05: the corpus started two days earlier, so every company looked "new"
    assert not has_history([0, 0, 0, 0, 0, 0, 4649, 2102])
    assert has_history([0, 0, 0, 3, 5, 4, 6, 9])


def test_theme_leaders_flag_a_new_leader() -> None:
    voice = {
        ("mediatek", "ai__on_device_ai", 2): 9,
        ("qualcomm", "ai__on_device_ai", 2): 4,
        ("qualcomm", "ai__on_device_ai", 1): 8,
        ("mediatek", "ai__on_device_ai", 1): 3,
        ("jedec", "ai__on_device_ai", 2): 11,  # an organisation: never a leader
        ("apple", "ai__foundation_models", 2): 2,  # theme too small to rank
    }
    totals = {
        ("ai__on_device_ai", 2): 12,
        ("ai__on_device_ai", 1): 10,
        ("ai__foundation_models", 2): 2,
    }
    [row] = theme_leaders(voice, totals, {"mediatek": "미디어텍"}, exclude=frozenset({"jedec"}))
    assert row.theme == "ai__on_device_ai" and row.leader_changed
    assert row.previous_leader == "qualcomm" and row.leaders[0].label == "미디어텍"
    assert (row.leaders[0].share, row.leaders[0].previous_share) == (75.0, 30.0)


def add_card(
    session: Session,
    source: Any,
    *,
    days_ago: float,
    companies: list[str] = (),  # type: ignore[assignment]
    keywords: list[str] = (),  # type: ignore[assignment]
    themes: tuple[str, ...] = ("ai__on_device_ai",),
    signal_type: str = "launch",
) -> None:
    n = next(_serial)
    url = f"https://{source.key}.example/c{n}"
    ingest_items(
        session,
        source,
        [RawItem(stable_id=url, url=url, title=f"company report {n}")],
        fetch_run=None,
        now=NOW - timedelta(days=days_ago),
        canary=True,
    )
    item = session.scalars(select(Item).where(Item.url == url)).one()
    session.add(
        ItemCard(
            item_id=item.id,
            status=CardStatus.READY,
            title_ko=f"기업 보도 {n}",
            summary_ko=[],
            keywords=list(keywords),
            companies=list(companies),
            input_hash=item.content_hash,
            generated_at=item.first_seen_at,
            field=themes[0].split("__")[0],
            themes=list(themes),
            signal_type=signal_type,
            impact="risk",
            scope="dx",
            relevance=70,
            taxonomy_revision=TAXONOMY_REVISION,
        )
    )
    session.flush()


@pytest.fixture
def corpus(db_session: Session) -> None:
    outlets = [
        build_source(key=f"outlet{i}", name=f"Outlet {i}", official_domain=f"outlet{i}.com")
        for i in range(5)
    ]
    newsroom = build_source(
        key="qcom",
        name="Qualcomm News",
        category="official_vendor",
        official_domain="qualcomm.com",
    )
    korean = build_source(
        key="kr", name="국내", region=Region.KR, language="ko", official_domain="kr.example"
    )
    db_session.add_all([*outlets, newsroom, korean])
    db_session.flush()
    # baseline: one research report a week on Saturdays (inside each paced window)
    for week in range(1, 8):
        add_card(
            db_session,
            outlets[0],
            days_ago=7 * week + 1,
            companies=["Qualcomm"],
            signal_type="research",
        )
    # this week: launches from five outlets and the newsroom, with Samsung named alongside
    for i in range(6):
        add_card(
            db_session,
            outlets[i % 5],
            days_ago=1 + i * 0.1,
            companies=["Qualcomm"],
            keywords=["삼성전자"] if i < 3 else [],
        )
    for i in range(2):
        add_card(db_session, newsroom, days_ago=2 + i * 0.1, companies=["Qualcomm"])
    # outside its main themes for the first time
    for i in range(3):
        add_card(
            db_session,
            outlets[i],
            days_ago=1.5,
            keywords=["스냅드래곤"],
            themes=("display_av__xr_spatial",),
        )
    # a name the registry does not know, three outlets
    for i in range(3):
        add_card(db_session, outlets[i], days_ago=0.5, companies=["Nova Haptics"])
    add_card(db_session, korean, days_ago=0.4, companies=["Samsung Electronics"])
    add_card(db_session, korean, days_ago=40, companies=["Samsung Electronics"])  # not a debut


def get(client: TestClient, headers: dict[str, str], path: str, **params: Any) -> Any:
    response = client.get(f"/api/public/{path}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.db
def test_company_radar_reads_momentum_self_share_entries_entrants_and_pairs(
    corpus: None, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    body = get(public_client, public_headers, "radar/companies", period="week", key="2026-W40")

    top = body["companies"][0]
    assert (top["key"], top["label"], top["relation"]) == ("qualcomm", "퀄컴", "supplier")
    assert top["counts"][-1] == 11 and top["self_reports"] == 2
    assert top["state"] == "surging"
    assert top["shift"]["signal_type"] == "launch" and top["baseline_mix"] == {"research": 7}
    assert {"key": "display_av__xr_spatial", "count": 3} in top["top_themes"]
    assert body["tagged"][-1] == 12  # unregistered names are not tags

    assert [(e["key"], e["theme"], e["count"]) for e in body["entries"]] == [
        ("qualcomm", "display_av__xr_spatial", 3)
    ]
    entrant = next(e for e in body["entrants"] if not e["registered"])
    assert (entrant["name"], entrant["cards"], entrant["sources"]) == ("Nova Haptics", 3, 3)
    pair = body["pairs"][0]
    assert (pair["a"], pair["b"], pair["count"], pair["is_new"]) == (
        "qualcomm",
        "samsungelectronics",
        3,
        True,
    )
    tones = {s["tone"]: s for s in body["signals"]}
    assert tones["company_surge"]["focus"] == {"kind": "company", "key": "qualcomm"}
    assert tones["new_entrant"]["focus"] == {"kind": "search", "key": "Nova Haptics"}


@pytest.mark.db
def test_company_topic_filter_and_reader_chips(
    corpus: None, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    detail = get(
        public_client,
        public_headers,
        "radar/topic",
        period="week",
        key="2026-W40",
        kind="company",
        value="qualcomm",
    )
    assert detail["profile"]["name"] == "Qualcomm" and detail["topic"]["label"] == "퀄컴"
    assert detail["companies"][0]["key"] == "samsungelectronics"

    theme = get(
        public_client,
        public_headers,
        "radar/topic",
        period="week",
        key="2026-W40",
        kind="theme",
        value="ai__on_device_ai",
    )
    assert {"qualcomm", "mediatek"} <= {c["key"] for c in theme["major_companies"]}

    items = get(
        public_client, public_headers, "items", company=["samsungelectronics"], period="30d"
    )
    assert items["total"] == 4  # three with Qualcomm, one Korean report this month
    chips = {c["key"]: c for item in items["items"] for c in item["companies"]}
    assert chips["samsungelectronics"] == {
        "key": "samsungelectronics",
        "label": "삼성전자",
        "relation": "self",
        "kind": "company",
    }
    bad = public_client.get(
        "/api/public/items", params={"company": "has space"}, headers=public_headers
    )
    assert bad.status_code == 422
