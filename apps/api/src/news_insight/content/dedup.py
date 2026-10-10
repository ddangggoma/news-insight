"""Duplicate keys, computed once at ingest so carding never sends the same story twice.

A random-sample study of all 257,866 items (2026-10-10) chose the keys, in this order:

1. `url`: the canonical URL without scheme, `www.`/`m.`, trailing slash and tracking
   parameters. The same Mastodon post reaches up to five hashtag feeds; the same BBC link
   arrives with and without `?at_campaign=rss`.
2. `text`: normalized title and body (NFKC, lower case, links, @mentions and #hashtags
   removed, punctuation folded), only from 40 characters on. The raw content hash also matched
   short pages that are not the same ("Home" at JEDEC and at ICO, two ICO notices about the same
   council); 4,109 items fell in such groups.
3. `link`: a social post that shares an article we already have takes that article's card
   (44 % of the linked Mastodon posts pointed at a domain we collect).
4. `title`: the same normalized title (30+ characters) when the bodies agree: one side has
   no real body (a Bluesky or HN post, an index entry), a body opens with the title, or both
   bodies start alike. Samples kept syndicated copies (Newsis/fnnews, heise/Mac & i,
   OpenAlex/arXiv) and rejected app-store pages for Android and iOS and different reports
   under one headline.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit

from news_insight.content.normalize import html_to_text

KEY_LENGTH = 32
MIN_TEXT = 40
MIN_TITLE = 30
LEAD = 120
TITLE_PREFIX = 60

# Mastodon renders a link as invisible/ellipsis/invisible spans, which text extraction splits
# into "https://www. example.com/path/to rest-of-path": up to two following fragments.
_URL_IN_TEXT = re.compile(r"https?://\S+(?:\s\S+){0,2}")
_MENTION = re.compile(r"(?<!\w)[@#][\w.-]+")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$|source$|cmpid$|ito$|at_)")


def normalize_text(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = _URL_IN_TEXT.sub(" ", value)
    value = _MENTION.sub(" ", value)
    return _NON_WORD.sub(" ", value).strip()


def normalize_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
    except ValueError:  # e.g. "Invalid IPv6 URL" from a link glued back together from text
        return url.strip().lower()
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k.lower()))
    )
    return f"{host}{parts.path.rstrip('/')}" + (f"?{query}" if query else "")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:KEY_LENGTH]


def url_key(url: str) -> str:
    return _digest(normalize_url(url))


@dataclass(frozen=True)
class DedupKeys:
    url: str
    text: str | None
    title: str | None
    lead: str | None  # opening of the body, for the title rule
    lead_title: bool  # the body opens with the title
    link: str | None  # url key of the article a social post shares


def dedup_keys(
    *, canonical: str, title: str, summary: str | None, body: str | None, link: str | None
) -> DedupKeys:
    norm_title = normalize_text(title)
    norm_body = normalize_text(summary or body)
    joined = f"{norm_title} | {norm_body}"
    return DedupKeys(
        url=url_key(canonical),
        text=_digest(joined) if len(norm_title) + len(norm_body) >= MIN_TEXT else None,
        title=_digest(norm_title) if len(norm_title) >= MIN_TITLE else None,
        lead=_digest(norm_body[:LEAD]) if len(norm_body) >= MIN_TEXT else None,
        lead_title=bool(norm_title) and norm_body.startswith(norm_title[:TITLE_PREFIX]),
        link=url_key(link) if link else None,
    )


def titles_agree(
    a_lead: str | None, a_lead_title: bool, b_lead: str | None, b_lead_title: bool
) -> bool:
    """Same title is the same story when the bodies do not say otherwise."""
    return a_lead is None or b_lead is None or a_lead_title or b_lead_title or a_lead == b_lead


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            values = dict(attrs)
            if values.get("href"):
                self.found.append((values["href"] or "", values.get("class") or ""))


def shared_link(html: str | None, *, post_url: str) -> str | None:
    """First external link of a social post (not a hashtag, mention or the post's own host)."""
    if not html or "<a" not in html:
        return None
    parser = _Links()
    parser.feed(html)
    try:
        own = (urlsplit(post_url).hostname or "").lower()
    except ValueError:
        own = ""
    for href, css in parser.found:
        try:
            parts = urlsplit(href)
            parts.hostname  # noqa: B018 (raises on a malformed host)
        except ValueError:
            continue
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host or host == own:
            continue
        if "mention" in css or "hashtag" in css or "/tags/" in parts.path:
            continue
        return href
    return None


def text_links(text: str | None) -> list[str]:
    """Candidate URLs in extracted text, gluing Mastodon's split spans back together (for
    items stored before links were kept): every way of joining up to two fragments."""
    out: list[str] = []
    for match in _URL_IN_TEXT.finditer(html_to_text(text) if text and "<" in text else text or ""):
        pieces = match.group(0).split()
        for n in range(len(pieces), 0, -1):
            out.append("".join(pieces[:n]).rstrip(".,;:!?)…"))
    return out
