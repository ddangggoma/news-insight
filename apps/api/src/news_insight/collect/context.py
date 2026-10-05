"""Build the collector input for a source: preset-resolved config plus credential headers."""

from datetime import datetime
from urllib.parse import quote, urlsplit

from news_insight.collect.contracts import CollectContext
from news_insight.collect.presets import effective_config
from news_insight.secrets import resolve_auth_headers
from news_insight.sources.models import Source


def collect_context(
    source: Source,
    *,
    now: datetime,
    etag: str | None = None,
    last_modified: str | None = None,
    last_success_at: datetime | None = None,
    known_ids: frozenset[str] = frozenset(),
) -> CollectContext:
    """Raises SecretError (credential) or ValueError (unknown preset)."""
    return CollectContext(
        endpoint_url=polite_url(source.endpoint_url),
        config=effective_config(source.config),
        now=now,
        etag=etag,
        last_modified=last_modified,
        last_success_at=last_success_at,
        headers=resolve_auth_headers(source.config),
        known_ids=known_ids,
    )


POLITE_HOSTS = frozenset({"api.openalex.org"})


def polite_url(url: str) -> str:
    """OpenAlex gives a contact address its larger "polite pool" quota (2026-10-05: 17 OpenAlex
    sources were answered 429). The address comes from OPENALEX_MAILTO in .env, never from the
    public catalog."""
    from news_insight.config import get_settings

    mailto = get_settings().openalex_mailto
    parts = urlsplit(url)
    if not mailto or parts.hostname not in POLITE_HOSTS or "mailto=" in parts.query:
        return url
    return f"{url}{'&' if parts.query else '?'}mailto={quote(mailto, safe='@')}"
