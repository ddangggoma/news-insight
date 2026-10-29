from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.config import Settings, get_settings
from news_insight.db import get_db
from news_insight.main import create_app
from news_insight.public import companies, radar
from news_insight.public.routes import get_now
from tests.public.seed import NOW

PUBLIC_KEY = "public-test-key"
CONSOLE_KEY = "console-test-key"


@pytest.fixture(autouse=True)
def _collecting_long_before(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The corpora plant only the reports a test needs, so the radar would take the first one
    for the start of collection and leave its window out of the baseline. Collection started
    long before unless a test reads the start from the data (`collection_start` marker)."""
    if request.node.get_closest_marker("collection_start"):
        return

    def since(_session: Session) -> datetime:
        return NOW - timedelta(days=400)

    monkeypatch.setattr(radar, "collection_start", since)
    monkeypatch.setattr(companies, "collection_start", since)


@pytest.fixture
def public_headers() -> dict[str, str]:
    return {"X-Public-Key": PUBLIC_KEY}


def _client(db_session: Session, settings: Settings) -> Iterator[TestClient]:
    app = create_app()

    def session_override() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: NOW
    with TestClient(app) as client:
        yield client


@pytest.fixture
def public_client(db_session: Session) -> Iterator[TestClient]:
    yield from _client(
        db_session,
        Settings(_env_file=None, public_api_key=PUBLIC_KEY, console_api_key=CONSOLE_KEY),
    )


@pytest.fixture
def unconfigured_client(db_session: Session) -> Iterator[TestClient]:
    yield from _client(db_session, Settings(_env_file=None, console_api_key=CONSOLE_KEY))
