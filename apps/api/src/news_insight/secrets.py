"""Source credentials: the catalog references secrets by name; values live only in env vars.

`config.auth.secret: GITHUB_TOKEN` reads `SOURCE_SECRET_GITHUB_TOKEN`. The prefix keeps a
catalog entry from pointing at unrelated variables such as the database password.
"""

import os
import re
from collections.abc import Mapping
from typing import Any

SECRET_PREFIX = "SOURCE_SECRET_"
SECRET_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,62}$")
HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class SecretError(Exception):
    """A referenced credential is malformed or not configured (never includes the value)."""


def secret_env_name(name: str) -> str:
    if not SECRET_NAME.fullmatch(name):
        raise SecretError(f"invalid secret name '{name}'")
    return SECRET_PREFIX + name


def _secret(name: Any, environ: Mapping[str, str]) -> str:
    env_name = secret_env_name(str(name or ""))
    value = environ.get(env_name, "").strip()
    if not value:
        raise SecretError(f"credential {env_name} is not configured")
    return value


def secret_value(name: str, *, environ: Mapping[str, str] = os.environ) -> str:
    """A named credential for collectors that sign requests themselves (EPO OPS)."""
    return _secret(name, environ)


def _header_name(name: Any) -> str:
    header = str(name or "")
    if not HEADER_NAME.fullmatch(header):
        raise SecretError(f"'{header}' is not a valid header name")
    return header


def resolve_auth_headers(
    config: Mapping[str, Any], *, environ: Mapping[str, str] = os.environ
) -> dict[str, str]:
    """Schemes: bearer (default), header (+ optional prefix, e.g. 'KakaoAK '), headers
    ({header: SECRET_NAME}, e.g. Naver's client id + secret pair)."""
    auth = config.get("auth")
    if auth is None:
        return {}
    if not isinstance(auth, Mapping):
        raise SecretError("config.auth must be a mapping")
    scheme = str(auth.get("scheme", "bearer"))
    if scheme == "headers":
        pairs = auth.get("headers")
        if not isinstance(pairs, Mapping) or not pairs:
            raise SecretError("config.auth.headers must map header names to secret names")
        return {_header_name(header): _secret(name, environ) for header, name in pairs.items()}
    value = _secret(auth.get("secret"), environ)
    if scheme == "bearer":
        return {"Authorization": f"Bearer {value}"}
    if scheme == "header":
        prefix = str(auth.get("prefix", ""))
        return {_header_name(auth.get("header")): f"{prefix}{value}"}
    raise SecretError(f"unsupported auth scheme '{scheme}'")
