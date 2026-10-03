"""Build the collector input for a source: preset-resolved config plus credential headers."""

from datetime import datetime

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
) -> CollectContext:
    """Raises SecretError (credential) or ValueError (unknown preset)."""
    return CollectContext(
        endpoint_url=source.endpoint_url,
        config=effective_config(source.config),
        now=now,
        etag=etag,
        last_modified=last_modified,
        last_success_at=last_success_at,
        headers=resolve_auth_headers(source.config),
    )
