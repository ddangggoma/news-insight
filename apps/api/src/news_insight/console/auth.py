"""Console API guard: the web server calls /api/admin over the internal network with a key."""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from news_insight.config import Settings, get_settings


def require_console_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_console_key: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.console_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "console API is disabled")
    if not x_console_key or not hmac.compare_digest(x_console_key, settings.console_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid console key")
