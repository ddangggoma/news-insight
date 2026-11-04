"""Hide stored items that are not articles (`news-insight items hide-junk`).

A source whose rules (config `link_pattern`, `exclude_pattern`) now refuse some pages still
holds the ones it took before. Nothing is deleted: the item's card is set to `failed` at the
attempt limit with a `hidden:` error. Every reader, radar, briefing, company and story query
needs a ready card, so the item leaves them all, and the carder only retries cards below the
attempt limit, so it stays out. Items already dated as archive (content/freshness.py) are out
of the reader anyway and are left alone.

Undo from the backup CSV: for each row set the card back to `old_status` / `old_attempts` /
`old_input_hash` / `old_error`, or delete the card when `had_card` is false.
"""

import csv
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.cards.service import MAX_ATTEMPTS
from news_insight.collect.pages import exclusion
from news_insight.content.freshness import fresh_condition
from news_insight.content.models import Item
from news_insight.sources.models import Source

HIDDEN = "hidden: "
BACKUP_COLUMNS = (
    "item_id",
    "source",
    "url",
    "title",
    "published_at",
    "first_seen_at",
    "had_card",
    "old_status",
    "old_attempts",
    "old_input_hash",
    "old_error",
    "old_scope",
)


@dataclass(frozen=True)
class Junk:
    item: Item
    card: ItemCard | None


def is_junk(
    url: str,
    config: Mapping[str, Any],
    *,
    hide: re.Pattern[str] | None = None,
    keep: re.Pattern[str] | None = None,
) -> bool:
    """The URL breaks the source's own rules (or `hide`), unless `keep` rescues it."""
    if keep is not None and keep.search(url):
        return False
    if hide is not None and hide.search(url):
        return True
    include = config.get("link_pattern")
    if include and not re.search(str(include), url):
        return True
    excluded = exclusion(config)
    return excluded is not None and excluded.search(url)


def find_junk(
    session: Session,
    source: Source,
    *,
    config: Mapping[str, Any] | None = None,
    hide: re.Pattern[str] | None = None,
    keep: re.Pattern[str] | None = None,
) -> tuple[list[Junk], int]:
    """(visible junk items with their card, junk items of any age). `config` defaults to the
    source's stored one; pass the catalog's before a deploy has copied it over."""
    rules = source.config if config is None else config
    rows = session.execute(
        select(Item, ItemCard)
        .options(defer(Item.body))
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .where(Item.source_id == source.id)
        .order_by(Item.id)
    ).all()
    fresh_ids = set(
        session.scalars(select(Item.id).where(Item.source_id == source.id, fresh_condition()))
    )
    total = 0
    visible: list[Junk] = []
    for item, card in rows:
        if not is_junk(item.url, rules, hide=hide, keep=keep):
            continue
        total += 1
        already = (
            card is not None
            and card.status is CardStatus.FAILED
            and ((card.error or "").startswith(HIDDEN))
        )
        if item.id in fresh_ids and not already:
            visible.append(Junk(item, card))
    return visible, total


def write_backup(path: Path, source: Source, junk: list[Junk]) -> None:
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(BACKUP_COLUMNS)
        for found in junk:
            card = found.card
            writer.writerow(
                [
                    found.item.id,
                    source.key,
                    found.item.url,
                    found.item.title,
                    _iso(found.item.published_at),
                    _iso(found.item.first_seen_at),
                    card is not None,
                    card.status.value if card else "",
                    card.attempts if card else "",
                    card.input_hash if card else "",
                    card.error if card else "",
                    card.scope if card else "",
                ]
            )


def hide(session: Session, junk: list[Junk], *, reason: str, now: datetime) -> int:
    for found in junk:
        message = f"{HIDDEN}{reason}"
        if found.card is None:
            session.add(
                ItemCard(
                    item_id=found.item.id,
                    status=CardStatus.FAILED,
                    input_hash=found.item.content_hash,
                    attempts=MAX_ATTEMPTS,
                    error=message,
                    generated_at=now,
                )
            )
        else:
            found.card.status = CardStatus.FAILED
            found.card.attempts = MAX_ATTEMPTS
            found.card.input_hash = found.item.content_hash  # not "changed since its card"
            found.card.error = message
    session.flush()
    return len(junk)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""
