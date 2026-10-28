"""Festival and season dates from 2009 to next year, computed from the Moon and the Sun.

Hindu lunar months run from new moon to new moon (amanta) and take the name of the sidereal sign the Sun enters during
the month (Lahiri ayanamsa); a month the Sun enters no sign in is a leap (adhika) month. A day starts at sunrise, taken
as 06:00 IST, so a date can be a day off from a printed panchang. Ramzan uses the Umm al-Qura calendar plus one day,
because India usually starts a day after Saudi Arabia.

    python festivals.py   # writes Data/festival_calendar.csv
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import ephem
import pandas as pd
from hijridate import Hijri

from eggdata import DATA

CALENDAR_PATH = DATA / "festival_calendar.csv"
FIRST_YEAR = 2009
# Next year too, so 14-day forecasts made in December still see January's festivals.
LAST_YEAR = max(2027, dt.date.today().year + 1)

ALL = ("chittoor", "chennai", "bengaluru", "namakkal", "kolkata", "vijayawada", "hyderabad")
SOUTH = ("chittoor", "chennai", "bengaluru", "namakkal", "vijayawada", "hyderabad")
TAMIL = ("chittoor", "chennai", "namakkal")
TELUGU_KANNADA = ("chittoor", "bengaluru", "vijayawada", "hyderabad")


@dataclass(frozen=True)
class Event:
    id: str
    name: str
    zones: tuple
    expected: str  # the demand effect people expect: "lower" or "higher"
    moves: bool  # dates shift from year to year
    note: str


EVENTS = (
    Event("summer", "Summer heat", ALL, "lower", False, "Fewer eggs are eaten in the hottest months."),
    Event("school-holidays", "School summer holidays", SOUTH, "lower", False,
          "No eggs in school meals in the southern states."),
    Event("chaitra-navratri", "Chaitra Navratri (North India)", ALL, "lower", True,
          "Nine days when many in North India avoid eggs and meat."),
    Event("ramzan", "Ramzan", ("kolkata", "hyderabad"), "higher", True,
          "Month of fasting, with evening meals that often include eggs and meat."),
    Event("sawan", "Sawan (North India)", ALL, "lower", True,
          "Holy month when many in North India avoid eggs and meat."),
    Event("shravana", "Shravana", TELUGU_KANNADA, "lower", True, "Holy month when many avoid eggs and meat."),
    Event("purattasi", "Purattasi", TAMIL, "lower", False, "Tamil month when many avoid eggs and meat."),
    Event("navratri", "Navratri (North India)", tuple(zone for zone in ALL if zone != "kolkata"), "lower", True,
          "Nine days when many in North India avoid eggs and meat."),
    Event("durga-puja", "Durga Puja", ("kolkata",), "higher", True, "Festival days in Bengal, with festive meals."),
    Event("kartik", "Kartik (North India)", ALL, "lower", True,
          "Holy month when many in North India avoid eggs and meat."),
    Event("karthika", "Karthika Masam", TELUGU_KANNADA, "lower", True,
          "Month after Diwali when many avoid eggs and meat."),
    Event("ayyappa", "Ayyappa season", SOUTH, "lower", False,
          "Sabarimala pilgrims avoid eggs and meat for 41 days or more."),
    Event("sankranti", "Sankranti and Pongal", SOUTH, "higher", False, "Harvest festival with festive meals."),
    Event("winter", "Winter", ALL, "higher", False, "More eggs are eaten in the cold months."),
    Event("christmas", "Christmas and New Year", ALL, "higher", False, "Cakes and baking use more eggs."),
)
EVENTS_BY_ID = {event.id: event for event in EVENTS}

_IST = dt.timedelta(hours=5, minutes=30)
_J2000 = ephem.Date("2000/1/1 12:00")
_MONTH_NAMES = ("chaitra", "vaishakha", "jyeshtha", "ashadha", "shravana", "bhadrapada",
                "ashvin", "kartika", "margashirsha", "pausha", "magha", "phalguna")
_SIGNS = {"kanya": 5, "tula": 6, "vrishchika": 7, "makara": 9}


@dataclass(frozen=True)
class _LunarMonth:
    name: str
    leap: bool
    new_moon: float
    next_new_moon: float


def _ist(moment: float) -> dt.datetime:
    return ephem.Date(moment).datetime() + _IST


def _sunrise_day(moment: float) -> dt.date:
    """The first day whose 06:00 IST sunrise comes after `moment`."""
    return (_ist(moment) + dt.timedelta(hours=18)).date()


def _sidereal_sun(moment: float) -> float:
    """The Sun's sidereal longitude in degrees, with an approximate Lahiri ayanamsa."""
    moment = ephem.Date(moment)
    tropical = math.degrees(ephem.Ecliptic(ephem.Sun(moment), epoch=moment).lon)
    ayanamsa = 23.857 + (moment - _J2000) / 365.25 * 50.28 / 3600
    return (tropical - ayanamsa) % 360


def _ingresses(start: float, end: float) -> list:
    """(moment, sign) each time the Sun enters a sidereal sign; sign 0 is Mesha."""
    found, moment = [], ephem.Date(start)
    while moment < end:
        sign = (math.floor(_sidereal_sun(moment) / 30) + 1) % 12
        low, high = moment, ephem.Date(moment + 32)
        for _ in range(40):
            middle = ephem.Date((low + high) / 2)
            if (_sidereal_sun(middle) - sign * 30 + 180) % 360 - 180 < 0:
                low = middle
            else:
                high = middle
        found.append((high, sign))
        moment = ephem.Date(high + 1)
    return found


def _lunar_months(start: float, end: float, ingresses: list) -> list:
    moons, moment = [], ephem.Date(start)
    while moment < end:
        moment = ephem.next_new_moon(moment)
        moons.append(moment)
        moment = ephem.Date(moment + 1)
    months = []
    for new_moon, next_new_moon in zip(moons, moons[1:]):
        signs = [sign for moment, sign in ingresses if new_moon <= moment < next_new_moon]
        months.append([_MONTH_NAMES[signs[0]] if signs else None, not signs, new_moon, next_new_moon])
    # A leap month takes the name of the regular month after it.
    for index, month in enumerate(months):
        if month[0] is None:
            month[0] = next((later[0] for later in months[index + 1:] if later[0]), "unknown")
    return [_LunarMonth(*month) for month in months]


def calendar() -> pd.DataFrame:
    """One row per event and year it starts in: event, year, start, end (both inclusive)."""
    start, end = ephem.Date(f"{FIRST_YEAR - 1}/11/1"), ephem.Date(f"{LAST_YEAR + 1}/3/1")
    ingresses = _ingresses(start, end)
    months = _lunar_months(start, end, ingresses)
    day = dt.timedelta(days=1)

    def lunar(name: str, year: int) -> _LunarMonth:
        return next(month for month in months
                    if month.name == name and not month.leap and _sunrise_day(month.new_moon).year == year)

    def whole_month(name: str, year: int) -> tuple:
        month = lunar(name, year)
        return _sunrise_day(month.new_moon), _sunrise_day(month.next_new_moon) - day

    def full_moon_month(previous: str, name: str, year: int) -> tuple:
        """North Indian (purnimanta) month: from the full moon in `previous` to the full moon in `name`."""
        first = ephem.next_full_moon(lunar(previous, year).new_moon)
        last = ephem.next_full_moon(lunar(name, year).new_moon)
        return _sunrise_day(first), _sunrise_day(last) - day

    def solar_day(sign: str, year: int, cutoff_hour: int) -> dt.date:
        """Day a solar month starts: the same day if the Sun moves sign before `cutoff_hour` IST, else the next."""
        moment = next(moment for moment, number in ingresses if number == _SIGNS[sign] and _ist(moment).year == year)
        return (_ist(moment) + dt.timedelta(hours=24 - cutoff_hour)).date()

    def ramzan(year: int) -> tuple:
        hijri_year = next(hijri for hijri in range(1425, 1455) if Hijri(hijri, 9, 1).to_gregorian().year == year)
        return Hijri(hijri_year, 9, 1).to_gregorian() + day, Hijri(hijri_year, 10, 1).to_gregorian()

    rows = []
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        navratri = _sunrise_day(lunar("ashvin", year).new_moon)
        chaitra = _sunrise_day(lunar("chaitra", year).new_moon)
        makara = solar_day("makara", year, 18)
        windows = {
            "summer": (dt.date(year, 4, 1), dt.date(year, 5, 31)),
            "school-holidays": (dt.date(year, 4, 20), dt.date(year, 6, 10)),
            "chaitra-navratri": (chaitra, chaitra + 8 * day),
            "ramzan": ramzan(year),
            "sawan": full_moon_month("ashadha", "shravana", year),
            "shravana": whole_month("shravana", year),
            # Tamil months start on the day of the Sun's move if it comes before sunset.
            "purattasi": (solar_day("kanya", year, 18), solar_day("tula", year, 18) - day),
            "navratri": (navratri, navratri + 8 * day),
            "durga-puja": (navratri + 5 * day, navratri + 9 * day),
            "kartik": full_moon_month("ashvin", "kartika", year),
            "karthika": whole_month("kartika", year),
            # Malayalam months start that day only if the Sun moves before about 13:00.
            "ayyappa": (solar_day("vrishchika", year, 13), solar_day("makara", year + 1, 18)),
            "sankranti": (makara - day, makara + 2 * day),
            "winter": (dt.date(year, 12, 1), dt.date(year + 1, 3, 1) - day),
            "christmas": (dt.date(year, 12, 15), dt.date(year + 1, 1, 1)),
        }
        rows += [(event, year, first, last) for event, (first, last) in windows.items()]
    table = pd.DataFrame(rows, columns=["event", "year", "start", "end"])
    return table.assign(start=pd.to_datetime(table.start), end=pd.to_datetime(table.end))


def read_calendar() -> pd.DataFrame:
    return pd.read_csv(CALENDAR_PATH, parse_dates=["start", "end"])


def write_calendar() -> pd.DataFrame:
    table = calendar()
    table.to_csv(CALENDAR_PATH, index=False, date_format="%Y-%m-%d", lineterminator="\n")
    return table


def daily_flags(days: pd.DatetimeIndex, occurrences: pd.DataFrame) -> pd.DataFrame:
    """True on the days inside each event; one column per event id."""
    flags = pd.DataFrame(False, index=days, columns=[event.id for event in EVENTS])
    for row in occurrences.itertuples():
        flags.loc[row.start:row.end, row.event] = True
    return flags


if __name__ == "__main__":
    table = write_calendar()
    print(f"Wrote {CALENDAR_PATH.relative_to(DATA.parent)}: {len(table)} rows, {FIRST_YEAR}–{LAST_YEAR}")
