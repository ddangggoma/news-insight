from news_insight.jobs.celery_app import celery_app, ping


def test_celery_runs_on_seoul_time() -> None:
    assert celery_app.conf.timezone == "Asia/Seoul"


def test_ping_task_executes() -> None:
    assert ping.apply().get() == "pong"


def test_beat_dispatches_due_sources_every_minute() -> None:
    assert celery_app.conf.beat_schedule["collect-dispatch-due"] == {
        "task": "collect.dispatch_due",
        "schedule": 60.0,
    }
