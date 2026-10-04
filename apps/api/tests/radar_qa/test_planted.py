"""Signal regression on the synthetic radar corpus (checklist QA-1, STAT-3).

`scripts/dev.sh radar-qa` seeds scripts/radar_demo_seed.py at a pinned time, exports the radar
responses with scripts/radar_qa_export.py and runs this file with RADAR_QA_DIR set. Each planted
pattern must be matched by its rule; ranking between matches is not checked, so a new random draw
in the seed does not break the test, but a rule or statistic that stops seeing a planted pattern
does. Skipped without RADAR_QA_DIR.
"""

import os
from pathlib import Path

import pytest

from news_insight.public.schemas import Radar
from news_insight.public.signals import radar_signals

DIR = os.environ.get("RADAR_QA_DIR")
VIEWS = ("week-2026-W39", "week-2026-W40", "month-2026-09", "quarter-2026-Q3")

pytestmark = pytest.mark.skipif(not DIR, reason="RADAR_QA_DIR not set (scripts/dev.sh radar-qa)")


def read(view: str) -> Radar:
    return Radar.model_validate_json(Path(DIR or "", f"{view}.json").read_text(encoding="utf-8"))


def candidates(view: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    radar_signals(read(view), candidates=found)
    return found


# view, rule, planted topic, what the seed planted
PLANTED = [
    ("month-2026-09", "surge", "ai__ai_agents", "AI agents surge"),
    ("month-2026-09", "surge", "robotics_mobility__humanoid_embodied", "humanoid surge"),
    ("week-2026-W40", "new", "유리기판", "glass substrate first appears"),
    ("week-2026-W40", "new", "하이브리드본딩", "hybrid bonding first appears"),
    ("month-2026-09", "new", "vla모델", "VLA first appears"),
    ("week-2026-W40", "back", "메타버스", "메타버스 returns after months of silence"),
    ("month-2026-09", "cool", "display_av__xr_spatial", "XR falls"),
    ("month-2026-09", "cool", "connectivity__cellular_5g_6g", "6G falls"),
    ("week-2026-W40", "early", "robotics_mobility__humanoid_embodied", "Embodied AI research-led"),
    ("month-2026-09", "early", "security__privacy_crypto", "PQC is research-led"),
    ("week-2026-W40", "shift", "display_av__display_panel", "OLED·MicroLED research → market"),
    ("month-2026-09", "shift", "display_av__display_panel", "OLED·MicroLED shift (month)"),
    ("week-2026-W40", "hype", "robotics_mobility__autonomous_driving", "robotaxi chatter"),
    ("week-2026-W40", "thin", "platform_sw__device_os", "One UI spike from one newsroom"),
    ("month-2026-09", "gap", "claudecode", "Claude Code: no Korean source"),
    ("quarter-2026-Q3", "gap", "webassembly", "WASM: no Korean source"),
    ("month-2026-09", "pull", "platform_sw__developer_tools", "coding agents: stars first"),
    ("week-2026-W39", "event", "스마트링", "health launch event day"),
    ("month-2026-09", "link", "동형암호×포스트양자암호", "PQC × homomorphic encryption"),
]


@pytest.mark.parametrize(("view", "tone", "key", "planted"), PLANTED)
def test_planted_pattern_is_found(view: str, tone: str, key: str, planted: str) -> None:
    assert key in candidates(view).get(tone, []), planted


def test_surges_keep_rising_in_their_second_week() -> None:
    # the agent and humanoid ramps start two weeks back: last week is already up, and a one-off
    # event day sits in the baseline, so this week reads as rising rather than a fresh surge
    themes = {t.key: t for t in read("week-2026-W40").themes}
    for key in ("ai__ai_agents", "robotics_mobility__humanoid_embodied"):
        assert themes[key].state in ("rising", "surging"), key


@pytest.mark.parametrize("view", VIEWS)
def test_falling_and_reactionless_themes_are_not_read_as_rising(view: str) -> None:
    found = candidates(view)
    assert "connectivity__cellular_5g_6g" not in found.get("surge", [])
    assert "display_av__xr_spatial" not in found.get("pull", [])  # XR barely gets stars


@pytest.mark.parametrize("view", VIEWS)
def test_every_view_yields_cards_once_per_theme(view: str) -> None:
    signals = radar_signals(read(view))
    assert len(signals) >= 6
    themes = [s.focus.key for s in signals if s.focus.kind == "theme"]
    assert len(set(themes)) == len(themes)
