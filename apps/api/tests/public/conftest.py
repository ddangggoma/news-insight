from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.config import Settings, get_settings
from news_insight.db import get_db
from news_insight.main import create_app

PUBLIC_KEY = "public-test-key"
CONSOLE_KEY = "console-test-key"


@pytest.fixture
def public_headers() -> dict[str, str]:
    return {"X-Public-Key": PUBLIC_KEY}


def _client(db_session: Session, settings: Settings) -> Iterator[TestClient]:
    app = create_app()

    def session_override() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
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
