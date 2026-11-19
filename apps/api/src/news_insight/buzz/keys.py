"""What a community post is matched by: the article it shares, the references it carries, its
title's MinHash, and who wrote it on which platform (design §4.2)."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from news_insight.buzz.models import BuzzItemKeys
from news_insight.content.models import Item, ItemDedup
from news_insight.sources.enums import AccessMethod, Track
from news_insight.sources.models import Source
from news_insight.stories.minhash import band_hashes, normalize_text, shingles, signature
from news_insight.stories.refs import extract_refs

WINDOW = timedelta(hours=24)  # posts that count towards a cluster
KEEP = timedelta(days=3)  # keys older than this are deleted
MIN_WORDS = 4  # shorter titles are matched by link and references only
INSERT_ROWS = 500

# one platform however many instances or entry points it has: a toot federated to three
# instances, or an HN story seen through Algolia and the front page, is one platform
PLATFORM_FAMILIES = {
    "Mastodon gGmbH": "fediverse",
    "Fosstodon": "fediverse",
    "mstdn.jp": "fediverse",
    "Algolia (HN Search)": "hn",
    "Y Combinator": "hn",
    "Bluesky Social PBC": "bluesky",
    "Meta Platforms": "threads",  # PR #156
    "Google LLC (YouTube Data API)": "youtube",
}

_URL = re.compile(r"https?://\s?\S+", re.IGNORECASE)
_TAG = re.compile(r"[#@]\s?[\w.@-]+")


def platform_of(operator: str, access_method: str) -> str:
    if operator in PLATFORM_FAMILIES:
        return PLATFORM_FAMILIES[operator]
    if access_method == AccessMethod.ACTIVITYPUB.value:
        return "fediverse"
    if operator.startswith("V2EX"):
        return "v2ex"
    return (operator.strip().lower() or "unknown")[:40]


def author_of(platform: str, author: str | None) -> str | None:
    name = (author or "").strip().lower().lstrip("@")
    return f"{platform}:{name}"[:340] if name else None


def clean_title(title: str) -> str:
    """The words of a post without links, hashtags and mentions: two posts sharing a link or a
    tag list are matched by those keys, not by their text."""
    return " ".join(_TAG.sub(" ", _URL.sub(" ", title)).split())


@dataclass(frozen=True)
class Keys:
    signature: list[int]
    bands: list[int]
    words: int
    refs: list[str]


def keys_for(title: str, summary: str | None, url: str) -> Keys:
    text = clean_title(title)
    words = len(normalize_text(text).split())
    refs = sorted(f"{kind}:{value}"[:300] for kind, value in extract_refs(url, title, summary))
    if words < MIN_WORDS:
        return Keys(signature=[], bands=[], words=words, refs=refs)
    sig = signature(shingles(text))
    return Keys(signature=sig, bands=band_hashes(sig), words=words, refs=refs)


def eligible() -> object:
    """Not a repeat of an earlier post, except a post sharing a known article (stored as a
    repeat of it, matched by its link): that is the community's own reaction (ruling R6)."""
    return or_(
        ItemDedup.item_id.is_(None),
        ItemDedup.duplicate_of.is_(None),
        ItemDedup.matched_by == "link",
    )


def compute_pending(session: Session, *, now: datetime, limit: int = 5000) -> int:
    """Keys for community posts of the window that have none yet; old keys are deleted."""
    rows = session.execute(
        select(Item, Source.operator, Source.access_method, ItemDedup.url_key, ItemDedup.link_key)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemDedup, ItemDedup.item_id == Item.id)
        .outerjoin(BuzzItemKeys, BuzzItemKeys.item_id == Item.id)
        .where(
            Item.track == Track.COMMUNITY,
            Item.first_seen_at >= now - WINDOW,
            BuzzItemKeys.item_id.is_(None),
            eligible(),  # type: ignore[arg-type]
        )
        .order_by(Item.first_seen_at.desc())
        .limit(limit)
    ).tuples()
    values = []
    for item, operator, access_method, url_key, link_key in rows:
        platform = platform_of(operator, str(access_method))
        keys = keys_for(item.title, item.summary, item.url)
        values.append(
            {
                "item_id": item.id,
                "platform": platform,
                "author": author_of(platform, item.author),
                "links": sorted({key for key in (url_key, link_key) if key}),
                "refs": keys.refs,
                "signature": keys.signature,
                "bands": keys.bands,
                "words": keys.words,
                "first_seen_at": item.first_seen_at,
                "computed_at": now,
            }
        )
    for start in range(0, len(values), INSERT_ROWS):
        session.execute(
            insert(BuzzItemKeys)
            .values(values[start : start + INSERT_ROWS])
            .on_conflict_do_nothing()
        )
    session.execute(delete(BuzzItemKeys).where(BuzzItemKeys.first_seen_at < now - KEEP))
    session.flush()
    return len(values)
