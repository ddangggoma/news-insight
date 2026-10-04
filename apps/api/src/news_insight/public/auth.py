"""Reader API guard: the web server calls /api/public with a key separate from the console."""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from news_insight.config import Settings, get_settings


def require_public_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_public_key: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.public_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "public API is disabled")
    if not x_public_key or not hmac.compare_digest(x_public_key, settings.public_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid public key")
