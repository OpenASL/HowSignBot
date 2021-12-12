import datetime as dt
from typing import NamedTuple

import holidays
from dateutil.easter import easter
from dateutil.relativedelta import FR
from dateutil.relativedelta import relativedelta as rd
from dateutil.relativedelta import SU


class Holiday(NamedTuple):
    emoji: str | None
    term: str | None = None  # search term to display on holidays


class USPlus(holidays.US):
    def _populate(self, year):
        super()._populate(year)

        # Assign solstices and equinoxes before holidays so that holidays
        #  take precedence if they fall on the same dates
        self[dt.date(2020, holidays.constants.DEC, 21)] = "Winter Solstice"
        self[dt.date(2021, holidays.constants.JUN, 20)] = "Summer Solstice"
        self[dt.date(2021, holidays.constants.MAR, 21)] = "Spring Equinox"
        self[dt.date(2021, holidays.constants.SEP, 22)] = "Autumnal Equinox"

        self[dt.date(year, holidays.constants.JAN, 15)] = "National Bagel Day"
        self[dt.date(year, holidays.constants.JAN, 24)] = "National Peanut Butter Day"
        self[dt.date(year, holidays.constants.JAN, 26)] = "Australia Day"
        self[dt.date(year, holidays.constants.JAN, 29)] = "Puzzle Day"
        self[
            dt.date(year, holidays.constants.FEB, 1)
        ] = "First Day of Black History Month"
        self[dt.date(year, holidays.constants.FEB, 2)] = "Groundhog Day"
        self[dt.date(year, holidays.constants.FEB, 5)] = "World Nutella Day"
        self[dt.date(year, holidays.constants.FEB, 9)] = "Pizza Day"
        self[dt.date(2021, holidays.constants.FEB, 12)] = "Chinese New Year (Ox)"
        self[dt.date(2022, holidays.constants.FEB, 1)] = "Chinese New Year (Tiger)"
        self[dt.date(year, holidays.constants.FEB, 14)] = "Valentine's Day"
        self[dt.date(year, holidays.constants.FEB, 27)] = "National Strawberry Day"
        self[dt.date(year, holidays.constants.MAR, 7)] = "Cereal Day"
        self[dt.date(year, holidays.constants.MAR, 14)] = "Pi Day"
        self[dt.date(year, holidays.constants.MAR, 17)] = "St. Patrick's Day"
        self[easter(year)] = "Easter"
        self[dt.date(year, holidays.constants.MAR, 20)] = "Earth Day"
        self[dt.date(year, holidays.constants.MAR, 26)] = "Purple Day"
        self[
            dt.date(year, holidays.constants.MAR, 31)
        ] = "International Transgender Day of Visibility"
        self[dt.date(year, holidays.constants.APR, 23)] = "National Picnic Day"
        self[dt.date(year, holidays.constants.APR, 26)] = "Pretzel Day"
        self[dt.date(year, holidays.constants.MAY, 1) + rd(weekday=FR(+1))] = "Space Day"
        self[dt.date(year, holidays.constants.MAY, 4)] = "Star Wars Day"
        self[
            dt.date(year, holidays.constants.MAY, 1) + rd(weekday=SU(+2))
        ] = "Mother's Day"
        self[dt.date(year, holidays.constants.MAY, 22)] = "World Turtle Day"
        self[dt.date(year, holidays.constants.MAY, 28)] = "National Hamburger Day"
        self[
            dt.date(year, holidays.constants.JUN, 1) + rd(weekday=SU(+3))
        ] = "Father's Day"
        self[dt.date(year, holidays.constants.JUN, 5)] = "National Donut Day"
        self[dt.date(year, holidays.constants.JUN, 14)] = "Flag Day"
        self[dt.date(year, holidays.constants.JUN, 19)] = "Juneteenth"
        self[dt.date(year, holidays.constants.JUN, 28)] = "Pride Day"
        self[
            dt.date(year, holidays.constants.JUL, 1) + rd(weekday=SU(+3))
        ] = "Ice Cream Day"
        self[dt.date(year, holidays.constants.JUL, 14)] = "Bastille Day"
        self[dt.date(year, holidays.constants.JUL, 17)] = "National Tattoo Day"
        self[dt.date(year, holidays.constants.JUL, 20)] = "National Lollipop Day"
        self[dt.date(year, holidays.constants.JUL, 23)] = "National Hot Dog Day"
        self[dt.date(year, holidays.constants.JUL, 24)] = "National Cousins Day"
        self[dt.date(year, holidays.constants.JUL, 31)] = "National Avocado Day"
        self[
            dt.date(year, holidays.constants.AUG, 1) + rd(weekday=FR(+1))
        ] = "International Beer Day"
        self[dt.date(year, holidays.constants.AUG, 8)] = "National Bowling Day"
        self[dt.date(year, holidays.constants.AUG, 24)] = "National Waffle Day"
        self[
            dt.date(year, holidays.constants.SEP, 19)
        ] = "International Talk Like A Pirate Day"
        self[dt.date(year, holidays.constants.SEP, 29)] = "National Coffee Day"
        self[dt.date(2021, holidays.constants.SEP, 27)] = "Yom Kippur"
        self[dt.date(2022, holidays.constants.OCT, 4)] = "Yom Kippur"
        self[dt.date(2023, holidays.constants.SEP, 24)] = "Yom Kippur"
        self[dt.date(year, holidays.constants.OCT, 4)] = "National Taco Day"
        self[dt.date(year, holidays.constants.OCT, 31)] = "Halloween"
        self[
            dt.date(year, holidays.constants.NOV, 1) + rd(weekday=FR(+4))
        ] = "Native American Heritage Day"
        self[dt.date(year, holidays.constants.NOV, 28)] = "National French Toast Day"
        self[dt.date(year, holidays.constants.DEC, 4)] = "National Cookie Day"
        self[dt.date(year, holidays.constants.DEC, 8)] = "National Brownie Day"
        self[dt.date(2020, holidays.constants.DEC, 10)] = "Hannukah"
        self[dt.date(2021, holidays.constants.NOV, 28)] = "Hannukah"
        self[dt.date(2022, holidays.constants.DEC, 18)] = "Hannukah"
        self[dt.date(2023, holidays.constants.DEC, 7)] = "Hannukah"
        self[dt.date(2024, holidays.constants.DEC, 26)] = "Hannukah"
        self[dt.date(year, holidays.constants.DEC, 24)] = "Christmas Eve"
        self[dt.date(year, holidays.constants.DEC, 31)] = "New Year's Eve"


def make_holidays(**kwargs):
    ca_holidays = holidays.CA(**kwargs)
    us_holidays = USPlus(**kwargs)
    return ca_holidays + us_holidays


_HOLIDAY_EMOJI_MAP = {
    "National Bagel Day": Holiday("🥯", "bagel"),
    "National Peanut Butter Day": Holiday("🥜", "peanut butter"),
    "Australia Day": Holiday("🇦🇺", "australia"),
    "Puzzle Day": Holiday("🧩", "puzzle"),
    "First Day of Black History Month": Holiday("🤟🏿", None),
    "Martin Luther King Jr. Day": Holiday("🤟🏿", "equality"),
    "Groundhog Day": Holiday("🐿", "groundhog"),
    "World Nutella Day": Holiday("🍫", None),
    "Pizza Day": Holiday("🍕", "pizza"),
    "Chinese New Year (Ox)": Holiday("🇨🇳", "ox"),
    "Chinese New Year (Tiger)": Holiday("🇨🇳", "tiger"),
    "Valentine's Day": Holiday("💘", "valentine"),
    "National Strawberry Day": Holiday("🍓", "strawberry"),
    "Easter": Holiday("🐰", "easter"),
    "Cereal Day": Holiday("🥣", "cereal"),
    "Pi Day": Holiday("🥧", "pie"),
    "St. Patrick's Day": Holiday("🍀", "saint patrick's day"),
    "Earth Day": Holiday("🌍", "earth"),
    "Purple Day": Holiday("🟣", "epilepsy"),
    "International Transgender Day of Visibility": Holiday("🏳️‍⚧️", "transgender"),
    "National Picnic Day": Holiday("🧺", "picnic"),
    "Pretzel Day": Holiday("🥨", "pretzel"),
    "Juneteenth": Holiday("🤟🏿", "liberation"),
    "Memorial Day": Holiday(None, "memorial day"),
    "Pride Day": Holiday("🏳️‍🌈", "pride"),
    "Canada Day": Holiday("🇨🇦", "canada"),
    "Independence Day": Holiday("🇺🇸", "independence day"),
    "Space Day": Holiday("🔭", "outer space"),
    "Star Wars Day": Holiday("☝", "star wars"),
    "Mother's Day": Holiday("👩‍👧", "mother's day"),
    "World Turtle Day": Holiday("🐢", "turtle"),
    "National Hamburger Day": Holiday("🍔", "hamburger"),
    "Father's Day": Holiday("👨‍👧", "father's day"),
    "National Donut Day": Holiday("🍩", "donut"),
    "Flag Day": Holiday("🇺🇸", "flag"),
    "Ice Cream Day": Holiday("🍦", "ice cream"),
    "National Hot Dog Day": Holiday("🌭", "hot dog"),
    "National Cousins Day": Holiday(None, "cousin"),
    "National Avocado Day": Holiday("🥑", "avocado"),
    "International Beer Day": Holiday("🍻", "beer"),
    "National Bowling Day": Holiday("🎳", "bowling"),
    "Bastille Day": Holiday("🇫🇷"),
    "National Tattoo Day": Holiday("🪡", "tattoo"),
    "National Lollipop Day": Holiday("🍭", "lollipop"),
    "National Waffle Day": Holiday("🧇", "waffle"),
    "International Talk Like A Pirate Day": Holiday("🏴‍☠️", "pirate"),
    "Celebrate Bisexuality Day": Holiday("🏳️‍🌈", "bisexual"),
    "Comic Book Day": Holiday("🦸🏽", "comic book"),
    "National Coffee Day": Holiday("☕️", "coffee"),
    "National Taco Day": Holiday("🌮", "taco"),
    "Yom Kippur": Holiday(None, "yom kippur"),
    "Halloween": Holiday("👻", "halloween"),
    "Labor Day": Holiday("⚒️️"),
    "Veterans Day": Holiday("🪖", "veterans day"),
    "Thanksgiving": Holiday("🦃", "thanksgiving"),
    "Native American Heritage Day": Holiday(None, "native american"),
    "National French Toast Day": Holiday("🍞", "french toast"),
    "National Cookie Day": Holiday("🍪", "cookie"),
    "National Brownie Day": Holiday("🍫", "brownie"),
    "Hannukah": Holiday("🕎", "hannukah"),
    "Christmas Eve": Holiday("🎄", "christmas eve"),
    "Christmas Day": Holiday("🎄", "christmas"),
    "New Year's Eve": Holiday("🥂", "new year's eve"),
    "New Year's Day": Holiday("🎆", "happy new year"),
    "Winter Solstice": Holiday("❄️", "solstice"),
    "Summer Solstice": Holiday("🏝", "solstice"),
    "Spring Equinox": Holiday("🌷", "equinox"),
    "Autumnal Equinox": Holiday("🍂", "equinox"),
}

HOLIDAYS = make_holidays()


def get(date: dt.date) -> Holiday | None:
    holiday_names = HOLIDAYS.get_list(date)
    if holiday_names:
        return _HOLIDAY_EMOJI_MAP.get(holiday_names[0], None)
    return None


def get_holiday_name(date: dt.date) -> Holiday | None:
    holiday_names = HOLIDAYS.get_list(date)
    if holiday_names:
        return holiday_names[0]
    return None
