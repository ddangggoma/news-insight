"""Text and URL normalization shared by the seen ledger and later phases."""

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "ref",
        "ref_src",
        "cmpid",
        "spm",
    }
)
TRACKING_PREFIXES = ("utm_",)
DEFAULT_PORTS = {"http": 80, "https": 443}
MAX_STABLE_ID = 500
_WHITESPACE = re.compile(r"\s+")


def canonical_url(url: str) -> str:
    """Lower-case scheme/host, drop default port, fragment and tracking params, sort query."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port is None or DEFAULT_PORTS.get(scheme) == port else f"{host}:{port}"
    path = parts.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMS and not key.lower().startswith(TRACKING_PREFIXES)
        )
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def html_to_text(value: str | None) -> str:
    """Strip markup, scripts and entities, then collapse whitespace."""
    if not value:
        return ""
    if "<" in value or "&" in value:
        tree = HTMLParser(value)
        tree.strip_tags(["script", "style", "noscript"])
        value = tree.body.text(separator=" ") if tree.body is not None else ""
    return _WHITESPACE.sub(" ", value).strip()


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def clean_text(value: str | None, *, limit: int | None = None) -> str | None:
    text = html_to_text(value)
    if not text:
        return None
    return truncate(text, limit) if limit is not None else text


def stable_key(stable_id: str) -> str:
    """Keep ids within the column limit; overlong ids become a deterministic digest."""
    stable_id = stable_id.strip()
    if len(stable_id) <= MAX_STABLE_ID:
        return stable_id
    return "sha256:" + hashlib.sha256(stable_id.encode("utf-8")).hexdigest()


def content_hash(*parts: str | None) -> str:
    """SHA-256 over normalized text, so markup or whitespace churn is not a change."""
    joined = "\x1f".join(html_to_text(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
