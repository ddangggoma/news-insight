import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.db


def test_pg_trgm_extension_is_installed(db_session: Session) -> None:
    installed = db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
    ).scalar_one_or_none()

    assert installed == "pg_trgm"


def test_server_is_postgres_16(db_session: Session) -> None:
    version_num = db_session.execute(text("SHOW server_version_num")).scalar_one()

    assert int(version_num) // 10000 == 16
