"""Community buzz clusters (화제 묶음) and breaking signals (속보), 2026-11-19 design
(docs/superpowers/specs/2026-11-19-community-signal-layer-design.md)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_insight.db import Base


class BuzzItemKeys(Base):
    """What a community post is matched by, computed once when it is first seen: re-hashing a
    day of posts (~12k MinHash signatures) every run took 13 s."""

    __tablename__ = "buzz_item_keys"
    __table_args__ = (Index("ix_buzz_item_keys_first_seen_at", "first_seen_at"),)

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    platform: Mapped[str] = mapped_column(String(40))  # operator family: fediverse, hn, threads…
    author: Mapped[str | None] = mapped_column(String(340))  # platform:author, lower case
    # URL keys (content/dedup.py) of the post and of the article it shares: an HN story's URL is
    # the article, a toot shares it as a link; either matches a news item's url_key
    links: Mapped[list[str]] = mapped_column(JSONB, default=list)
    refs: Mapped[list[str]] = mapped_column(JSONB, default=list)  # kind:value
    signature: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    bands: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    words: Mapped[int] = mapped_column(default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BuzzCluster(Base):
    """Community posts about one thing. Counted without bots and feed accounts; over the
    threshold it is 화제 (`crossed_at`), and 속보 (`breaking`) when no news had it then."""

    __tablename__ = "buzz_clusters"
    __table_args__ = (
        Index("ix_buzz_clusters_last_seen_at", "last_seen_at"),
        Index(
            "ix_buzz_clusters_crossed_at",
            "crossed_at",
            postgresql_where=text("crossed_at IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    post_count: Mapped[int] = mapped_column(default=0)  # every member in the window
    human_posts: Mapped[int] = mapped_column(default=0)  # without bots and feed accounts
    author_count: Mapped[int] = mapped_column(default=0)
    platform_count: Mapped[int] = mapped_column(default=0)
    platforms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    heat: Mapped[float] = mapped_column(Float, default=0.0)  # sum of positive platform z
    score: Mapped[float] = mapped_column(Float, default=0.0)
    lead_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
    crossed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    breaking: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    breaking_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    news_item_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    news_first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    news_caught_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # one Korean summary per cluster instead of a card per post
    title_ko: Mapped[str | None] = mapped_column(Text)
    summary_ko: Mapped[list[str]] = mapped_column(JSONB, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_event: Mapped[bool | None] = mapped_column(Boolean)
    relevant: Mapped[bool | None] = mapped_column(Boolean)
    summary_engine: Mapped[str | None] = mapped_column(String(20))
    summary_model: Mapped[str | None] = mapped_column(String(80))
    summarized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_posts: Mapped[int] = mapped_column(default=0)  # human posts when last summarised
    summary_count: Mapped[int] = mapped_column(default=0)
    summary_attempts: Mapped[int] = mapped_column(default=0)
    summary_tried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_error: Mapped[str | None] = mapped_column(Text)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    push_channels: Mapped[list[str]] = mapped_column(JSONB, default=list)
    merged_into: Mapped[int | None] = mapped_column(
        ForeignKey("buzz_clusters.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BuzzClusterItem(Base):
    """A post's cluster. A post belongs to one cluster at a time; merges move it."""

    __tablename__ = "buzz_cluster_items"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("buzz_clusters.id", ondelete="CASCADE"), index=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
