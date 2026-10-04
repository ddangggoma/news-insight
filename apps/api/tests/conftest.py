import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import redis
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from news_insight.config import Settings, get_settings
from news_insight.db import get_db
from news_insight.main import create_app

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://news:news-dev-password@localhost:8720/news_insight_test",
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:8721/15")


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    database = make_url(TEST_DATABASE_URL).database or ""
    if not database.endswith("_test"):
        raise RuntimeError(f"Refusing to reset non-test database '{database}'")
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    config = Config(str(API_ROOT / "alembic.ini"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def redis_client() -> Iterator[redis.Redis]:
    if not TEST_REDIS_URL.rstrip("/").endswith("/15"):
        raise RuntimeError("Refusing to flush a non-test Redis database (use db 15)")
    client = redis.Redis.from_url(TEST_REDIS_URL)
    client.flushdb()
    yield client
    client.flushdb()
    client.close()


# console API client shared by console and briefing tests
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
