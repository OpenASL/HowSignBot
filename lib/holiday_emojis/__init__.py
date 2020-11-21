import datetime as dt

import holidays
from dateutil.easter import easter
from dateutil.relativedelta import relativedelta as rd, FR


class USPlus(holidays.US):
    def _populate(self, year):
        super()._populate(year)
        self[
            dt.date(year, holidays.constants.FEB, 1)
        ] = "First Day of Black History Month"
        self[dt.date(year, holidays.constants.FEB, 2)] = "Groundhog Day"
        self[dt.date(year, holidays.constants.FEB, 5)] = "World Nutella Day"
        self[dt.date(year, holidays.constants.FEB, 14)] = "Valentine's Day"
        self[dt.date(year, holidays.constants.MAR, 14)] = "Pi Day"
        self[dt.date(year, holidays.constants.MAR, 17)] = "St. Patrick's Day"
        self[easter(year)] = "Easter"
        self[dt.date(year, holidays.constants.MAR, 20)] = "Earth Day"
        self[
            dt.date(year, holidays.constants.MAR, 31)
        ] = "International Transgender Day of Visibility"
        self[dt.date(year, holidays.constants.MAY, 5)] = "Cinco de Mayo"
        self[dt.date(year, holidays.constants.JUN, 19)] = "Juneteenth"
        self[dt.date(year, holidays.constants.JUN, 28)] = "Pride Day"
        self[dt.date(year, holidays.constants.JUL, 14)] = "Bastille Day"
        self[dt.date(year, holidays.constants.OCT, 31)] = "Halloween"
        self[
            dt.date(year, holidays.constants.NOV, 1) + rd(weekday=FR(+4))
        ] = "Native American Heritage Day"


def make_holidays(**kwargs):
    ca_holidays = holidays.CA(**kwargs)
    us_holidays = USPlus(**kwargs)
    return ca_holidays + us_holidays


EMOJIS = {
    "First Day of Black History Month": "🤟🏿",
    "Martin Luther King Jr. Day": "🤟🏿",
    "Groundhog Day": "🐿",
    "World Nutella Day": "🍫",
    "Valentine's Day": "💘",
    "Easter": "🐰",
    "Pi Day": "🥧",
    "St. Patrick's Day": "🍀",
    "Earth Day": "🌍",
    "International Transgender Day of Visibility": "🏳️‍⚧️",
    "Juneteenth": "🤟🏿",
    "Pride Day": "🏳️‍🌈",
    "Canada Day": "🇨🇦",
    "Independence Day": "🇺🇸",
    "Cinco de Mayo": "🇲🇽",
    "Bastille Day": "🇫🇷",
    "Halloween": "👻",
    "Labor Day": "⚒️️",
    "Thanksgiving": "🦃",
    "Christmas Day": "🎄",
    "New Year's Eve": "🥂",
}


def get(date: dt.date) -> str:
    holidays = make_holidays()
    holiday_name = holidays.get(date)
    return EMOJIS.get(holiday_name, "")
