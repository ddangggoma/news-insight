from datetime import UTC, datetime

from news_insight.collect.macros import expand_macros

NOW = datetime(2026, 10, 3, 0, 30, tzinfo=UTC)


def test_today_offsets_use_kst_dates() -> None:
    template = "pushed:>{today-30d} created:>{today-180d} on {today}"

    assert expand_macros(template, now=NOW) == (
        "pushed:>2026-09-03 created:>2026-04-06 on 2026-10-03"
    )


def test_kst_day_boundary() -> None:
    assert expand_macros("{today}", now=datetime(2026, 10, 2, 16, 0, tzinfo=UTC)) == "2026-10-03"


def test_other_braces_are_untouched() -> None:
    assert expand_macros("{yesterday} {today-x}", now=NOW) == "{yesterday} {today-x}"
