import pytest

import pytz

import pytz_informal


@pytest.mark.parametrize(
    ("input_value", "expected"),
    (
        ("EST", "America/New_York"),
        ("EDT", "America/New_York"),
        ("edt", "America/New_York"),
        ("Edt", "America/New_York"),
        ("CST", "America/Chicago"),
        ("MST", "America/Denver"),
        ("PDT", "America/Los_Angeles"),
    ),
)
def test_find(input_value, expected):
    assert pytz_informal.timezone(input_value) == pytz.timezone(expected)


def test_handle_invalid():
    with pytest.raises(pytz.UnknownTimeZoneError):
        pytz_informal.timezone("eat")
