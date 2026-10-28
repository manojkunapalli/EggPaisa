"""Outside data: daily weather from NASA POWER and monthly world feed prices from the World Bank.

Weather: NASA Langley Research Center (LaRC) POWER Project, funded through the NASA Earth Science/Applied Science
Program. Feed: World Bank Commodity Price Data (The Pink Sheet), CC BY 4.0.

    python outside_data.py   # downloads both into Data/
"""
from __future__ import annotations

import io
import ssl
import time
import urllib.request

import pandas as pd

from eggdata import DATA, daily_prices

WEATHER_PATH = DATA / "weather_daily.csv"
FEED_PATH = DATA / "feed_monthly.csv"
POWER_URL = (
    "https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M_MAX,RH2M,PRECTOTCORR"
    "&community=AG&latitude={lat}&longitude={lon}&start={start}&end={end}&format=CSV"
)
PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)
# Zone id -> (latitude, longitude) of the city.
PLACES = {
    "chittoor": (13.22, 79.10),
    "chennai": (13.08, 80.27),
    "bengaluru": (12.97, 77.59),
    "namakkal": (11.22, 78.17),
    "kolkata": (22.57, 88.36),
    "vijayawada": (16.51, 80.65),
    "hyderabad": (17.39, 78.49),
}


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "EggPaisa/0.1 (egg price research)"})
    with urllib.request.urlopen(request, timeout=120, context=ssl.create_default_context()) as response:
        return response.read()


def download_weather() -> pd.DataFrame:
    """Daily maximum temperature (°C), humidity (%) and rain (mm) for each zone, 2009 to the latest NECC day."""
    start, end = "20090101", f"{daily_prices().index.max():%Y%m%d}"
    frames = []
    for zone, (lat, lon) in PLACES.items():
        text = _get(POWER_URL.format(lat=lat, lon=lon, start=start, end=end)).decode()
        lines = text.splitlines()
        table = pd.read_csv(io.StringIO("\n".join(lines[lines.index("-END HEADER-") + 1:])))
        dates = pd.to_datetime(table.YEAR.astype(str), format="%Y") + pd.to_timedelta(table.DOY - 1, unit="D")
        frames.append(pd.DataFrame({
            "date": dates, "zone": zone,
            "tmax": table.T2M_MAX, "humidity": table.RH2M, "rain": table.PRECTOTCORR,
        }).replace(-999, float("nan")))
        time.sleep(1)
    weather = pd.concat(frames).dropna()
    weather.to_csv(WEATHER_PATH, index=False, date_format="%Y-%m-%d", lineterminator="\n")
    return weather


def download_feed() -> pd.DataFrame:
    """Monthly world maize and soybean meal prices, US$ per tonne."""
    sheet = pd.read_excel(io.BytesIO(_get(PINK_SHEET_URL)), sheet_name="Monthly Prices", skiprows=4)
    sheet = sheet.rename(columns={sheet.columns[0]: "month"}).iloc[1:]  # the first row holds units
    feed = pd.DataFrame({
        "month": pd.to_datetime(sheet.month.astype(str), format="%YM%m"),
        "maize": pd.to_numeric(sheet["Maize"], errors="coerce"),
        "soybean_meal": pd.to_numeric(sheet["Soybean meal"], errors="coerce"),
    })
    feed = feed[feed.month >= "2008-01-01"].dropna()
    feed.to_csv(FEED_PATH, index=False, date_format="%Y-%m", lineterminator="\n")
    return feed


def read_weather() -> pd.DataFrame:
    return pd.read_csv(WEATHER_PATH, parse_dates=["date"])


def read_feed() -> pd.DataFrame:
    return pd.read_csv(FEED_PATH, parse_dates=["month"])


if __name__ == "__main__":
    weather, feed = download_weather(), download_feed()
    print(f"Weather: {len(weather):,} rows to {weather.date.max():%d %b %Y}; "
          f"feed: {len(feed)} months to {feed.month.max():%b %Y}")
