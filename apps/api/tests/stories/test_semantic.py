from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.cards.engines import EngineOutput
from news_insight.sources.enums import Track
from news_insight.stories import semantic
from news_insight.stories.models import Relation, Story, StoryItem, StoryMergeCheck
from news_insight.stories.semantic import identifiers, plausible, run, words
from news_insight.stories.service import cluster
from tests.stories.test_cluster import NOW, add, scope_for

LECUN_EN = 'LeCun has "zero concerns" about AI wiping out humanity, recent rogue incidents'
LECUN_KO = "LeCun, AI의 인류 멸종과 최근 ‘일탈’ 사건에 “전혀 우려 없다”"
OTHER = "Samsung opens a new display research center in Asan for microLED panels"


def test_identifiers_tell_template_bulletins_apart() -> None:
    assert not plausible(
        "🟠 CVE-2026-105211 - High (8.1) ZITADEL before 4.17.1 contains an auth bypass",
        "🟠 CVE-2026-105212 - High (7.5) ZITADEL 3.x before 3.4.14 allows token reuse",
    )
    assert not plausible(
        "Possible Phishing 🎣 on: hxxps[:]//quantumcuverify[.]weebly[.]com/ Analysis at",
        "Possible Phishing 🎣 on: hxxps[:]//ptt-qwh[.]com[.]cn Analysis at",
    )
    assert identifiers("see https://example.com/a1b2 for Qwen3.8 notes") == {"qwen3.8"}
    # links differ between reposts of one story and are ignored
    assert plausible(
        "OpenAI safety leader quits, warning culture is broken https://t.co/abc123",
        "OpenAI safety leader quits, warning culture is broken https://bsky.app/x9",
    )


def test_short_titles_are_too_generic_but_cjk_counts() -> None:
    assert not plausible("Research Projects", "Research Programs")
    assert words("Galaxy首款夾式耳機 搶先在韓國推出") >= 4
    assert plausible(
        "Galaxy首款夾式耳機 搶先在韓國推出", "Galaxy初のクリップ型イヤホン。まずは韓国から"
    )


class FakeJudge:
    def __init__(self) -> None:
        self.asked = 0

    def __call__(self, prompt: str, schema: dict[str, Any]) -> EngineOutput:
        self.asked += 1
        same = "LeCun has" in prompt and "인류 멸종" in prompt
        return EngineOutput(raw={"pairs": [{"id": 0, "same": same}]}, model="fake")


def fake_embed(texts: list[str]) -> list[list[float]]:
    # the two LeCun titles point the same way, everything else elsewhere
    def vector(text: str) -> list[float]:
        if "LeCun" in text:
            return [1.0, 0.1 if "AI의" in text else 0.0, 0.0]
        return [0.0, 0.0, 1.0]

    return [vector(t) for t in texts]


pytestmark = pytest.mark.db


def test_a_judged_embedding_neighbour_merges_two_stories(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(semantic, "INSERT_ROWS", 2)  # three titles, two INSERTs
    add(db_session, "verge", Track.NEWS, [("https://verge.com/lecun", LECUN_EN, "", [], 60)])
    add(db_session, "etnews", Track.NEWS, [("https://etnews.com/lecun", LECUN_KO, "", [], 80)])
    add(db_session, "zdnet", Track.NEWS, [("https://zdnet.com/oled", OTHER, "", [], 50)])
    cluster(scope_for(db_session), now=NOW)
    assert db_session.scalar(select(func.count()).select_from(Story)) == 3

    judge = FakeJudge()
    stats = run(db_session, embed=fake_embed, ask=judge, model="m", now=NOW)

    assert (stats.embedded, stats.candidates, stats.merged) == (3, 1, 1)
    assert db_session.scalar(select(func.count()).select_from(Story)) == 2
    merged = db_session.scalars(select(Story).where(Story.item_count == 2)).one()
    assert merged.source_count == 2 and merged.title_ko == LECUN_KO  # higher relevance leads
    relations = sorted(
        r.value
        for r in db_session.scalars(
            select(StoryItem.relation).where(StoryItem.story_id == merged.id)
        )
    )
    assert relations == [Relation.SEED.value, Relation.SEMANTIC.value]
    assert db_session.scalar(select(StoryMergeCheck.same)) is True

    again = run(db_session, embed=fake_embed, ask=judge, model="m", now=NOW)
    assert (again.embedded, again.candidates, judge.asked) == (0, 0, 1)


def test_a_rejected_pair_stays_apart_and_is_not_asked_again(db_session: Session) -> None:
    add(db_session, "verge", Track.NEWS, [("https://verge.com/lecun", LECUN_EN, "", [], 60)])
    add(
        db_session,
        "etnews",
        Track.NEWS,
        [
            (
                "https://etnews.com/lecun2",
                "LeCun keynote at a robotics summit in Seoul next month",
                "",
                [],
                80,
            )
        ],
    )
    cluster(scope_for(db_session), now=NOW)
    judge = FakeJudge()

    def same_direction(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    first = run(db_session, embed=same_direction, ask=judge, model="m", now=NOW)
    second = run(db_session, embed=same_direction, ask=judge, model="m", now=NOW)
    assert (first.candidates, first.merged, second.candidates, judge.asked) == (1, 0, 0, 1)
    assert db_session.scalar(select(func.count()).select_from(Story)) == 2
