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


def test_beat_climbs_candidates_every_ten_minutes() -> None:
    entry = celery_app.conf.beat_schedule["sources-auto-validate"]

    assert entry == {"task": "sources.auto_validate", "schedule": 600.0}


def test_beat_clusters_stories_every_five_minutes() -> None:
    assert celery_app.conf.beat_schedule["stories-cluster"] == {
        "task": "stories.cluster",
        "schedule": 300.0,
    }
