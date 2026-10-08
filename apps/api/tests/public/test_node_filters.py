from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.taxonomy.seed import backfill_labels, seed_taxonomy
from news_insight.watchlist import service as watchlist
from tests.public.seed import seed_corpus
from tests.public.test_items_api import feed, titles

pytestmark = pytest.mark.db


@pytest.fixture
def labelled(db_session: Session) -> dict[str, int]:
    found = seed_corpus(db_session)
    seed_taxonomy(db_session)
    backfill_labels(db_session)
    return found


def test_node_filter_takes_any_scheme_and_depth_with_descendants(
    public_client: TestClient, public_headers: dict[str, str], labelled: dict[str, int]
) -> None:
    def pick(**params: Any) -> set[str]:
        return set(titles(feed(public_client, public_headers, **params)))

    by_field = pick(field="display_av")
    assert pick(node="technology:display_av") == by_field  # the field node covers its themes
    assert pick(node="technology:display_av__display_panel") == pick(
        theme="display_av__display_panel"
    )
    assert pick(node="signal_type:launch") == pick(signal="launch")
    assert (
        pick(node=["signal_type:launch", "technology:display_av"])
        == pick(signal="launch") | by_field
    )
    bad = public_client.get(
        "/api/public/items", params={"node": "no colon"}, headers=public_headers
    )
    assert bad.status_code == 422


def test_watch_a_node_of_any_depth(db_session: Session, labelled: dict[str, int]) -> None:
    watch = watchlist.add(db_session, kind="node", value="technology:display_av")
    assert watch.label == "디스플레이·영상·오디오"
    with pytest.raises(watchlist.WatchError):
        watchlist.add(db_session, kind="node", value="technology:nope")
    now = datetime.now(UTC)
    hits = watchlist.hits(db_session, start=now - timedelta(days=30), end=now + timedelta(days=1))
    assert any(h.kind == "node" and h.count >= 1 for h in hits)


def _distribution(client: TestClient, headers: dict[str, str], **params: Any) -> Any:
    return client.get(
        "/api/public/radar/distribution",
        params={"period": "month", "key": "2026-10", **params},
        headers=headers,
    )


def test_distribution_rolls_up_to_any_depth_under_a_base_node(
    public_client: TestClient, public_headers: dict[str, str], labelled: dict[str, int]
) -> None:
    fields = _distribution(public_client, public_headers, depth=1).json()
    display = next(n for n in fields["nodes"] if n["key"] == "display_av")
    assert display["count"] == len(
        set(titles(feed(public_client, public_headers, field="display_av", period="30d")))
    )
    assert fields["depth"] == 1 and {s["key"] for s in fields["schemes"]} >= {
        "technology",
        "signal_type",
    }

    themes = _distribution(
        public_client, public_headers, depth=1, root="technology:display_av"
    ).json()
    assert themes["depth"] == 2 and themes["root"]["key"] == "display_av"
    assert {n["parent_key"] for n in themes["nodes"]} == {"display_av"}
    assert sum(n["count"] for n in themes["nodes"]) >= display["count"]
    signals = _distribution(public_client, public_headers, scheme="signal_type").json()
    assert signals["nodes"] and all(n["depth"] == 1 for n in signals["nodes"])
    assert _distribution(public_client, public_headers, scheme="nope").status_code == 422
    assert _distribution(public_client, public_headers, root="technology:nope").status_code == 422
