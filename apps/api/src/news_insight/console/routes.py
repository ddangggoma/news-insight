"""Operations console API. Reached only by the web server over the internal network (D16)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from news_insight.console import queries
from news_insight.console.auth import require_console_key
from news_insight.console.schemas import Overview
from news_insight.db import get_db

router = APIRouter(
    prefix="/api/admin", tags=["console"], dependencies=[Depends(require_console_key)]
)
DB = Annotated[Session, Depends(get_db)]


@router.get("/overview")
def get_overview(session: DB) -> Overview:
    return queries.overview(session, now=datetime.now(UTC))
