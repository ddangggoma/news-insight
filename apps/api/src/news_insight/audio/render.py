"""Render the spoken briefing on the macOS host and keep an index next to the files.

`say` writes AIFF, `afconvert` turns it into 64 kbps AAC (.m4a), which every browser and
podcast app plays. Caddy serves the directory at /media with range requests; the API reads
`index.json` to tell readers which briefings have audio.
"""

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

Runner = Callable[..., subprocess.CompletedProcess[str]]
SUBDIR = "briefings"
INDEX = "index.json"
KEEP = 60  # newest entries in the index (files older than that stay on disk)


class AudioEntry(BaseModel):
    briefing_date: str
    version: int
    file: str
    bytes: int
    seconds: int
    voice: str
    headline: str
    generated_at: datetime

    @property
    def url(self) -> str:
        return f"/media/{SUBDIR}/{self.file}"


class AudioError(Exception):
    """`say` or `afconvert` failed (not macOS, voice missing, disk full)."""


def _folder(media_dir: str) -> Path:
    return Path(media_dir) / SUBDIR


def entries(media_dir: str) -> list[AudioEntry]:
    """Indexed recordings, newest first; an unreadable index reads as none."""
    try:
        raw = json.loads((_folder(media_dir) / INDEX).read_text("utf-8"))
        return [AudioEntry.model_validate(row) for row in raw.get("items", [])]
    except (OSError, ValueError):
        return []


def entry_for(media_dir: str, briefing_date: str, version: int) -> AudioEntry | None:
    return next(
        (
            e
            for e in entries(media_dir)
            if e.briefing_date == briefing_date and e.version == version
        ),
        None,
    )


def _seconds(path: Path, runner: Runner) -> int:
    done = runner(["afinfo", str(path)], capture_output=True, text=True, check=False)
    for line in (done.stdout or "").splitlines():
        if "duration" in line:
            try:
                return round(float(line.split(":", 1)[1].split()[0]))
            except (IndexError, ValueError):
                break
    return 0


def render(
    script: str,
    *,
    media_dir: str,
    briefing_date: str,
    version: int,
    headline: str,
    voice: str,
    rate: int,
    now: datetime,
    runner: Runner = subprocess.run,
) -> AudioEntry:
    folder = _folder(media_dir)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{briefing_date}-v{version}.m4a"
    with tempfile.TemporaryDirectory(prefix="briefing-audio-") as work:
        text, aiff = Path(work) / "script.txt", Path(work) / "speech.aiff"
        text.write_text(script, "utf-8")
        steps = [
            ["say", "-v", voice, "-r", str(rate), "-f", str(text), "-o", str(aiff)],
            ["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000", str(aiff), str(folder / name)],
        ]
        for step in steps:
            try:
                done = runner(step, capture_output=True, text=True, check=False, timeout=600)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise AudioError(f"{step[0]}: {exc}") from exc
            if done.returncode != 0:
                raise AudioError(f"{step[0]} exited {done.returncode}: {done.stderr[-200:]}")
    path = folder / name
    seconds = _seconds(path, runner)
    if seconds < 5:  # a voice that is not downloaded renders near-silence (2026-10-06: Eddy)
        path.unlink(missing_ok=True)
        raise AudioError(f"voice {voice} produced {seconds}s of audio; is it installed?")
    entry = AudioEntry(
        briefing_date=briefing_date,
        version=version,
        file=name,
        bytes=path.stat().st_size,
        seconds=seconds,
        voice=voice,
        headline=headline,
        generated_at=now,
    )
    others = [
        e for e in entries(media_dir) if (e.briefing_date, e.version) != (briefing_date, version)
    ]
    rows: list[dict[str, Any]] = [
        e.model_dump(mode="json")
        for e in sorted([entry, *others], key=lambda e: (e.briefing_date, e.version), reverse=True)
    ][:KEEP]
    index = folder / INDEX
    staged = index.with_suffix(".tmp")
    staged.write_text(json.dumps({"items": rows}, ensure_ascii=False, indent=1), "utf-8")
    os.replace(staged, index)
    return entry
