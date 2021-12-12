import datetime as dt
from typing import Optional
from typing import Tuple

import dateparser
import pytz
from pytz.tzinfo import StaticTzInfo

import pytz_informal


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


PACIFIC = pytz.timezone("America/Los_Angeles")
MOUNTAIN = pytz.timezone("America/Denver")
CENTRAL = pytz.timezone("America/Chicago")
EASTERN = pytz.timezone("America/New_York")

# EDT and PDT change to EST and PST during the winter
# Show the current name in docs
EASTERN_CURRENT_NAME = utcnow().astimezone(EASTERN).strftime("%Z")
PACIFIC_CURRENT_NAME = utcnow().astimezone(PACIFIC).strftime("%Z")

# Timezone is omitted because it is computed using tzinfo.tzname
TIME_FORMAT = "%-I:%M %p "
TIME_FORMAT_NO_MINUTES = "%-I %p "


def normalize_timezone(dtime: dt.datetime) -> dt.datetime:
    """Normalizes informal N. American timezones ("EST", "PST") to
    the IANA timezones ("America/Los_Angeles", "America/New_York")
    """
    tzinfo = dtime.tzinfo
    assert tzinfo is not None
    naive = dtime.replace(tzinfo=None)
    tzname = tzinfo.tzname(naive)
    assert tzname is not None
    tzone = pytz_informal.timezone(tzname)
    return tzone.localize(naive)


class NoTimeZoneError(ValueError):
    pass


def parse_human_readable_datetime(
    dstr: str,
    settings: Optional[dict] = None,
    user_timezone: Optional[pytz.BaseTzInfo] = None,
    # By default, use Pacific time if timezone can't be parsed
    fallback_timezone: Optional[pytz.BaseTzInfo] = PACIFIC,
) -> Tuple[Optional[dt.datetime], Optional[dt.tzinfo]]:
    parsed = dateparser.parse(dstr, settings=settings)
    if parsed is None:
        return None, None
    if not parsed.tzinfo:
        if user_timezone is not None:
            parsed = user_timezone.localize(parsed)
        else:
            if not fallback_timezone:
                raise NoTimeZoneError(f"Time zone could not be parsed from {dstr}.")
            parsed = fallback_timezone.localize(parsed)
    parsed = normalize_timezone(parsed)
    used_timezone = parsed.tzinfo
    return parsed.astimezone(dt.timezone.utc), used_timezone


def display_timezone(tzinfo: StaticTzInfo, dtime: dt.datetime) -> str:
    # Pass is_dst False to handle ambiguous datetimes
    # NOTE: America/Los_Angeles will still display correctly as PDT after DST ends
    ret = tzinfo.tzname(dtime.replace(tzinfo=None), is_dst=False)
    assert ret is not None
    return ret


def display_time(dtime: dt.datetime, time_format: str, tzinfo: pytz.BaseTzInfo) -> str:
    return dtime.astimezone(tzinfo).strftime(time_format) + display_timezone(
        tzinfo, dtime
    )


def format_multi_time(dtime: dt.datetime) -> str:
    time_format = TIME_FORMAT if dtime.minute != 0 else TIME_FORMAT_NO_MINUTES
    pacific_dstr = display_time(dtime, time_format, tzinfo=PACIFIC)
    mountain_dstr = display_time(dtime, time_format, tzinfo=MOUNTAIN)
    central_dstr = display_time(dtime, time_format, tzinfo=CENTRAL)
    eastern_dstr = display_time(dtime, time_format, tzinfo=EASTERN)
    return " / ".join((pacific_dstr, mountain_dstr, central_dstr, eastern_dstr))
