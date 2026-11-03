"""One spelling per AI model across leaderboards, and the lookup that resolves a site's name."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import AiModel, AiModelAlias

_PARENS = re.compile(r"\([^)]*\)")
_SEPARATORS = re.compile(r"[\s_.]+")
_HYPHENS = re.compile(r"-{2,}")
# a release date at the end: -20261015 or -2026-06-01
_DATE_SUFFIX = re.compile(r"-(?:20\d{6}|\d{4}-\d{2}-\d{2})$")


def normalize(name: str) -> str:
    """Lower case, spaces/underscores/dots → hyphens, repeated hyphens collapsed, parenthesised
    parts (the site's configuration, e.g. "(High)") and a trailing release date dropped."""
    text = _PARENS.sub(" ", name.strip()).lower()
    text = _HYPHENS.sub("-", _SEPARATORS.sub("-", text)).strip("-")
    return _DATE_SUFFIX.sub("", text)


def resolve_model(session: Session, raw: str, org: str | None) -> int | None:
    """The model a site's `raw` name belongs to, or None: aliases are matched as written first,
    then the normalized spelling against aliases and model names. Nothing is ever created:
    an unmatched name stays on its score row until the console links it. `org` is not used
    for matching yet (names are unique across organisations)."""
    wanted = raw.strip()
    found = session.scalar(select(AiModelAlias.model_id).where(AiModelAlias.alias == wanted))
    if found is not None:
        return found
    slug = normalize(wanted)
    if not slug:
        return None
    found = session.scalar(select(AiModelAlias.model_id).where(AiModelAlias.alias == slug))
    if found is not None:
        return found
    return session.scalar(select(AiModel.id).where(AiModel.name == slug))
