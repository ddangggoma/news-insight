from typing import Any

from celery import Celery

from news_insight.config import get_settings

BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "collect-dispatch-due": {"task": "collect.dispatch_due", "schedule": 60.0},
}


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
