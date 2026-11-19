"""Breaking pushes (design §6): the watchdog's ntfy topic and Telegram chat, from the app.

The 2026-10-05 "no alerts" decision was lifted on 2026-11-19 for this one kind of push. A
cluster is pushed once, when it is breaking, summarised as a concrete IT event, still not told by
any news, and at most PUSH_FRESH old; never more than `signal_push_max_per_hour` an hour or
`signal_push_max_per_day` a KST day, and never in the quiet hours (00-07 KST by default).
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.buzz.models import BuzzCluster
from news_insight.cards.service import KST, in_quiet_hours
from news_insight.config import Settings

logger = logging.getLogger(__name__)
PUSH_FRESH = timedelta(hours=3)
Poster = Callable[[str, bytes, dict[str, str]], int]


def http_post(url: str, body: bytes, headers: dict[str, str]) -> int:
    response = httpx.post(url, content=body, headers=headers, timeout=15.0)
    return response.status_code


class Notifier:
    """ntfy and Telegram, each optional; one failing channel does not stop the other."""

    def __init__(self, settings: Settings, post: Poster = http_post) -> None:
        self._settings, self._post = settings, post

    def channels(self) -> list[str]:
        names = []
        if self._settings.signal_ntfy_topic:
            names.append("ntfy")
        if self._settings.signal_telegram_bot_token and self._settings.signal_telegram_chat_id:
            names.append("telegram")
        return names

    def send(self, title: str, message: str, link: str) -> list[str]:
        delivered = []
        for name in self.channels():
            try:
                ok = (self._ntfy if name == "ntfy" else self._telegram)(title, message, link)
            except Exception as exc:  # noqa: BLE001 - one channel must not stop the other
                logger.warning("buzz push %s failed: %s", name, exc)
                ok = False
            if ok:
                delivered.append(name)
        return delivered

    def _ntfy(self, title: str, message: str, link: str) -> bool:
        s = self._settings
        body = {
            "topic": s.signal_ntfy_topic,
            "title": title,
            "message": message,
            "priority": 4,
            "tags": ["zap"],
            "click": link,
        }
        headers = {"Content-Type": "application/json"}
        if s.signal_ntfy_token:
            headers["Authorization"] = f"Bearer {s.signal_ntfy_token}"
        code = self._post(
            (s.signal_ntfy_server or "https://ntfy.sh").rstrip("/"),
            json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers,
        )
        return 200 <= code < 300

    def _telegram(self, title: str, message: str, link: str) -> bool:
        s = self._settings
        body = {
            "chat_id": s.signal_telegram_chat_id,
            "text": f"{title}\n{message}\n{link}",
            "disable_web_page_preview": True,
        }
        code = self._post(
            f"https://api.telegram.org/bot{s.signal_telegram_bot_token}/sendMessage",
            json.dumps(body, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
        return 200 <= code < 300


@dataclass
class PushStats:
    due: int = 0
    sent: int = 0
    held: str | None = None  # why nothing went out: off, quiet hours, a limit, no channel
    channels: list[str] = field(default_factory=list)


def message_of(cluster: BuzzCluster, base_url: str) -> tuple[str, str, str]:
    title = f"[속보] {cluster.title_ko}"
    lines = list(cluster.summary_ko[:2])
    people = f"커뮤니티 {cluster.platform_count}곳·{cluster.author_count}명이 이야기 중"
    lines.append(f"{people}, 아직 뉴스 보도 없음")
    return title, "\n".join(lines), f"{base_url.rstrip('/')}/buzz#c{cluster.id}"


def due(session: Session, *, now: datetime) -> list[BuzzCluster]:
    return list(
        session.scalars(
            select(BuzzCluster)
            .where(
                BuzzCluster.breaking.is_(True),
                BuzzCluster.pushed_at.is_(None),
                BuzzCluster.merged_into.is_(None),
                BuzzCluster.summarized_at.is_not(None),
                BuzzCluster.is_event.is_(True),
                BuzzCluster.relevant.is_(True),
                BuzzCluster.news_caught_up_at.is_(None),
                BuzzCluster.breaking_at >= now - PUSH_FRESH,
            )
            .order_by(BuzzCluster.score.desc(), BuzzCluster.id)
        )
    )


def _pushed_since(session: Session, since: datetime) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(BuzzCluster).where(BuzzCluster.pushed_at >= since)
        )
        or 0
    )


def push_due(
    session: Session, notifier: Notifier, settings: Settings, *, now: datetime
) -> PushStats:
    clusters = due(session, now=now)
    stats = PushStats(due=len(clusters))
    if not clusters:
        return stats
    if not settings.signal_push:
        stats.held = "off"
        return stats
    if in_quiet_hours(settings.signal_push_quiet_hours, now):
        stats.held = "quiet hours"
        return stats
    if not notifier.channels():
        stats.held = "no channel"
        return stats
    midnight = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    room = min(
        settings.signal_push_max_per_hour - _pushed_since(session, now - timedelta(hours=1)),
        settings.signal_push_max_per_day - _pushed_since(session, midnight),
    )
    for cluster in clusters:
        if room <= 0:
            stats.held = "limit"
            break
        title, message, link = message_of(cluster, settings.public_base_url)
        delivered = notifier.send(title, message, link)
        if not delivered:
            stats.held = "every channel failed"
            break  # the next run tries again while the cluster is fresh
        cluster.pushed_at, cluster.push_channels = now, delivered
        stats.sent += 1
        stats.channels = sorted(set(stats.channels) | set(delivered))
        room -= 1
    session.flush()
    return stats
