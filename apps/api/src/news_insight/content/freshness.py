"""Archive pages are not news (2026-10-05 audit).

An item published long before we first saw it came from a site's archive (a sitemap or a
crawler finding an old page), not from today's news. It gets no card and stays out of the
reader, the radar and the briefing; it is kept so the collector does not fetch it again.
"""

from datetime import timedelta

from sqlalchemy import ColumnElement, or_

from news_insight.content.models import Item

ARCHIVE_AFTER = timedelta(days=30)


def fresh_condition() -> ColumnElement[bool]:
    """Items without a date, or published at most ARCHIVE_AFTER before we first saw them."""
    return or_(Item.published_at.is_(None), Item.published_at >= Item.first_seen_at - ARCHIVE_AFTER)
