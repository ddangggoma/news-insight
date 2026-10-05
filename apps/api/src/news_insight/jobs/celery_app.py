from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from news_insight.config import get_settings

BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "collect-dispatch-due": {"task": "collect.dispatch_due", "schedule": 60.0},
    "sources-run-canaries": {"task": "sources.run_canaries", "schedule": 3600.0},
    "sources-auto-validate": {"task": "sources.auto_validate", "schedule": 600.0},
    "stories-cluster": {"task": "stories.cluster", "schedule": 300.0},
    "ops-check": {"task": "ops.check", "schedule": 300.0},
    "radar-warm": {"task": "radar.warm", "schedule": 600.0},
    "briefing-freeze": {
        "task": "briefing.freeze",
        "schedule": crontab(hour=4, minute=40),  # D15 freeze, 20 min before publication
    },
    "sources-quality": {
        "task": "sources.quality",
        "schedule": crontab(hour=3, minute=30),  # V5/V6 daily, before the 04:40 freeze
    },
    "technologies-refresh": {
        "task": "technologies.refresh",
        "schedule": crontab(hour=3, minute=45),  # keys and labels after registry edits
    },
    "content-purge-expired": {
        "task": "content.purge_expired",
        "schedule": crontab(hour=3, minute=15),  # Asia/Seoul (celery timezone)
    },
}


@setup_logging.connect
def _json_logs(**_: Any) -> None:
    """Celery keeps its own handlers unless this signal is connected."""
    import sys

    from news_insight.observability import configure_logging

    configure_logging("scheduler" if "beat" in sys.argv else "worker")


def create_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "news_insight",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["news_insight.jobs.tasks"],
    )
    app.conf.update(
        timezone=settings.timezone,
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_default_queue="default",
        beat_schedule=BEAT_SCHEDULE,
    )
    return app


celery_app = create_celery()


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"
