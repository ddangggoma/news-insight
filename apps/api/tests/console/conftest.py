from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.config import Settings, get_settings
from news_insight.db import get_db
from news_insight.main import create_app

CONSOLE_KEY = "test-key"


@pytest.fixture
def headers() -> dict[str, str]:
    return {"X-Console-Key": CONSOLE_KEY}


@pytest.fixture
def console_client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()

    def session_override() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, console_api_key=CONSOLE_KEY
    )
    with TestClient(app) as client:
        yield client
