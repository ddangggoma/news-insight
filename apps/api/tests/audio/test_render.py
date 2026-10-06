import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from news_insight.audio.render import AudioError, entries, entry_for, render
from news_insight.audio.script import speakable

NOW = datetime(2026, 10, 6, 20, 5, tzinfo=UTC)


def fake_runner(seconds: float = 42.0, fail: str | None = None) -> Any:
    calls: list[list[str]] = []

    def run(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[0] == fail:
            return subprocess.CompletedProcess(args, 1, "", "boom")
        if args[0] == "say":
            Path(args[args.index("-o") + 1]).write_bytes(b"aiff")
        elif args[0] == "afconvert":
            Path(args[-1]).write_bytes(b"m4a-bytes")
        elif args[0] == "afinfo":
            return subprocess.CompletedProcess(args, 0, f"estimated duration: {seconds} sec\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    run.calls = calls  # type: ignore[attr-defined]
    return run


def _render(tmp_path: Path, day: str, version: int, runner: Any) -> Any:
    return render(
        "스크립트",
        media_dir=str(tmp_path),
        briefing_date=day,
        version=version,
        headline="헤드라인",
        voice="Yuna",
        rate=185,
        now=NOW,
        runner=runner,
    )


def test_render_speaks_converts_and_indexes_newest_first(tmp_path: Path) -> None:
    runner = fake_runner()
    _render(tmp_path, "2026-10-05", 4, runner)
    entry = _render(tmp_path, "2026-10-06", 1, runner)

    assert entry.url == "/media/briefings/2026-10-06-v1.m4a" and entry.seconds == 42
    assert entry.bytes == len(b"m4a-bytes")
    say = runner.calls[0]
    assert say[:5] == ["say", "-v", "Yuna", "-r", "185"]
    assert [e.briefing_date for e in entries(str(tmp_path))] == ["2026-10-06", "2026-10-05"]
    assert entry_for(str(tmp_path), "2026-10-05", 4) is not None
    assert entry_for(str(tmp_path), "2026-10-05", 3) is None
    index = json.loads((tmp_path / "briefings" / "index.json").read_text("utf-8"))
    assert len(index["items"]) == 2


def test_silent_or_failed_renders_raise(tmp_path: Path) -> None:
    with pytest.raises(AudioError, match="installed"):
        _render(tmp_path, "2026-10-06", 1, fake_runner(seconds=0.02))
    assert not (tmp_path / "briefings" / "2026-10-06-v1.m4a").exists()
    with pytest.raises(AudioError, match="afconvert exited 1"):
        _render(tmp_path, "2026-10-06", 1, fake_runner(fail="afconvert"))
    assert entries(str(tmp_path)) == []


def test_speakable_drops_links_and_symbols() -> None:
    assert speakable("NPU·GPU 비교 https://x.io/a **강조** 5G/6G") == "NPU, GPU 비교 강조 5G 6G"
