import datetime as dt

from freezegun import freeze_time
import pytest
import pytz

from bot.utils.datetimes import parse_human_readable_datetime, display_timezone


@pytest.mark.parametrize(
    "value",
    (
        "today 8:25pm edt",
        "today 2pm edt",
        "today at 2pm edt",
        "tomorrow 2pm pdt",
        "on friday at 2pm cst",
        "9/25 2:30 pm cdt",
    ),
)
@freeze_time("2020-09-25 14:00:00")
def test_parse_human_readable_datetime(value, snapshot):
    dtime, _ = parse_human_readable_datetime(value)
    assert dtime.tzinfo == dt.timezone.utc
    assert dtime.isoformat() == snapshot


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (pytz.timezone("America/New_York"), "EDT"),
        (pytz.timezone("America/Los_Angeles"), "PDT"),
    ),
)
def test_display_timezone(value, expected):
    dtime = dt.datetime(2020, 9, 25, tzinfo=dt.timezone.utc)
    assert display_timezone(value, dtime) == expected
