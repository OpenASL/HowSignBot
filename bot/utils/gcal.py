import datetime as dt
from urllib.parse import urlencode


def create_gcal_url(
    text,
    start: dt.datetime,
    end: dt.datetime | None = None,
    description: str | None = None,
):
    dt_format = "%Y%m%dT%H%M%SZ"
    base_url = "http://www.google.com/calendar/event"
    end = end or start + dt.timedelta(hours=1)
    params = {
        "action": "TEMPLATE",
        "text": text,
        "dates": f"{start.strftime(dt_format)}/{end.strftime(dt_format)}",
    }
    if description:
        params["details"] = description
    return "?".join((base_url, urlencode(params)))
