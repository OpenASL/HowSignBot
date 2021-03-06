import datetime as dt

from freezegun import freeze_time

from bot.exts.practices.daily_message import get_daily_handshape


@freeze_time("2020-09-25 14:00:00")
def test_get_daily_handshape():
    todays_handshape = get_daily_handshape()
    assert todays_handshape == get_daily_handshape()
    assert todays_handshape != get_daily_handshape(dt.datetime(2020, 9, 26))
