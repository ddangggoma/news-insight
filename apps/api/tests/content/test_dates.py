from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from news_insight.content.dates import earliest, plausible, source_timezone, stated_date

SEOUL = ZoneInfo("Asia/Seoul")
SHANGHAI = ZoneInfo("Asia/Shanghai")
SEEN = datetime(2026, 10, 26, 23, 30, tzinfo=UTC)  # 08:30 KST on the 27th


def test_region_picks_the_zone_and_config_overrides_it() -> None:
    assert source_timezone("kr") == SEOUL
    assert source_timezone("greater_china") == SHANGHAI
    assert source_timezone("global_en") == ZoneInfo("UTC")
    assert source_timezone("kr", {"timezone": "Asia/Tokyo"}) == ZoneInfo("Asia/Tokyo")
    assert source_timezone("kr", {"timezone": "Not/AZone"}) == ZoneInfo("UTC")


def test_keeps_past_dates_and_drops_parse_errors() -> None:
    past = SEEN - timedelta(days=3)
    assert plausible(past, seen=SEEN, tz=SEOUL) == past
    assert plausible(SEEN + timedelta(minutes=5), seen=SEEN, tz=SEOUL) == SEEN + timedelta(
        minutes=5
    )
    assert plausible(datetime(1970, 1, 1, tzinfo=UTC), seen=SEEN, tz=SEOUL) is None
    assert plausible(None, seen=SEEN, tz=SEOUL) is None


def test_wall_clock_read_as_utc_is_moved_back_by_the_source_offset() -> None:
    # "2026-10-27 08:09:31" from a Seoul feed, read as UTC: nine hours in the future
    wrong = datetime(2026, 10, 27, 8, 9, 31, tzinfo=UTC)
    assert plausible(wrong, seen=SEEN, tz=SEOUL) == datetime(2026, 10, 26, 23, 9, 31, tzinfo=UTC)
    # ZOL labels Beijing time with "Z"
    zol = datetime(2026, 10, 27, 7, 0, tzinfo=UTC)
    assert plausible(zol, seen=SEEN, tz=SHANGHAI) == datetime(2026, 10, 26, 23, 0, tzinfo=UTC)


def test_future_dates_that_no_offset_explains_are_dropped() -> None:
    assert plausible(SEEN + timedelta(days=3), seen=SEEN, tz=SEOUL) is None
    assert plausible(SEEN + timedelta(hours=2), seen=SEEN, tz=ZoneInfo("UTC")) is None


def test_revisions_keep_the_first_date() -> None:
    first, edit = SEEN - timedelta(days=2), SEEN
    assert earliest(first, edit) == first
    assert earliest(None, edit) == edit
    assert earliest(first, None) == first


def test_datelines_in_the_text() -> None:
    cases = {
        "[디지털투데이 홍길동 기자] 입력 2026.10.26 14:30 본문": datetime(2026, 10, 26, 5, 30),
        "기사입력 2026-10-26 오후 2:05 | 수정 2026-10-27": datetime(2026, 10, 26, 5, 5),
        "발행일 : 2026년 10월 25일": datetime(2026, 10, 24, 15, 0),
        "发布时间：2026年10月26日 09:15": datetime(2026, 10, 26, 0, 15),
    }
    for text, expected in cases.items():
        assert stated_date(text, seen=SEEN, tz=SEOUL) == (expected.replace(tzinfo=UTC)), text


def test_datelines_must_be_plausible_and_labelled() -> None:
    assert stated_date("2026.10.26 행사가 열린다", seen=SEEN, tz=SEOUL) is None  # no label
    assert stated_date("입력 2026.12.01 10:00", seen=SEEN, tz=SEOUL) is None  # future
    assert stated_date("입력 2026.02.30", seen=SEEN, tz=SEOUL) is None  # no such day
    assert stated_date(None, seen=SEEN, tz=SEOUL) is None
