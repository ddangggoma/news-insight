from news_insight.jobs.celery_app import celery_app, ping


def test_celery_runs_on_seoul_time() -> None:
    assert celery_app.conf.timezone == "Asia/Seoul"


def test_ping_task_executes() -> None:
    assert ping.apply().get() == "pong"


def test_beat_schedule_covers_collection_canary_and_retention() -> None:
    schedule = celery_app.conf.beat_schedule

    assert schedule["collect-dispatch-due"] == {"task": "collect.dispatch_due", "schedule": 60.0}
    assert schedule["sources-run-canaries"]["task"] == "sources.run_canaries"
    assert schedule["content-purge-expired"]["task"] == "content.purge_expired"
