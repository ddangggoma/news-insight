from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.audio.script import build_script
from news_insight.config import get_settings
from news_insight.public.briefings import public_briefing
from tests.audio.test_render import NOW, fake_runner
from tests.public.test_briefings_api import published

pytestmark = pytest.mark.db


def test_briefing_script_and_audio_listing(
    db_session: Session,
    public_client: TestClient,
    public_headers: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "media_dir", str(tmp_path))
    briefing = published(db_session)
    view = public_briefing(db_session, briefing)

    script = build_script(view)

    assert script.startswith("10월 5일 데일리 브리핑입니다.\n헤드라인.")
    assert "첫째 인사이트" in script and script.endswith("이상 오늘의 브리핑이었습니다.")
    assert view.audio is None
    from news_insight.audio.render import render

    render(
        script,
        media_dir=str(tmp_path),
        briefing_date=str(briefing.briefing_date),
        version=briefing.version,
        headline="헤드라인",
        voice="Yuna",
        rate=185,
        now=NOW,
        runner=fake_runner(),
    )
    body = public_client.get("/api/public/briefings/latest", headers=public_headers).json()
    listed = public_client.get("/api/public/audio", headers=public_headers).json()

    assert body["audio"] == {
        "url": f"/media/briefings/{briefing.briefing_date}-v1.m4a",
        "seconds": 42,
    }
    assert listed[0]["url"] == body["audio"]["url"] and listed[0]["headline"] == "헤드라인"
