"""Phase 5: the app's High-price months screen -> EggPaisa/Resources/necc_month_pattern.json.

Each month's average NECC price ÷ the centred 12-month average around it, median across years, scaled so the
12 months average 0%. Each zone's festivals and seasons come with their coming dates and their effect from
Data/festival_effects.csv. exploration.ipynb shows the results.
"""
from __future__ import annotations

import json
import math

import pandas as pd

import festivals
from eggdata import RESOURCES, app_zones, zone_prices
from festival_effects import EFFECTS_PATH

PATTERN_PATH = RESOURCES / "necc_month_pattern.json"
METHOD = ("Monthly average NECC price ÷ centred 12-month average; median across years; "
          "low/high = 25th/75th percentile; scaled so the 12 months average 0%.")


def complete_months(prices: pd.DataFrame) -> pd.DataFrame:
    """Monthly averages; the current month counts only once it is complete."""
    cutoff = (prices.index.max() + pd.Timedelta(days=1)).replace(day=1)
    return prices[prices.index < cutoff].resample("MS").mean()


def ratio_to_trend(monthly: pd.DataFrame) -> pd.DataFrame:
    trend = monthly.rolling(12).mean().rolling(2).mean().shift(-6)  # centred 2x12 moving average
    return monthly / trend


def month_pattern(zone_ratio: pd.Series) -> pd.DataFrame:
    """Per calendar month: % vs the yearly average, its 25th–75th percentile range, and years above average."""
    values = zone_ratio.dropna()
    by_month = values.groupby(values.index.month)
    median = by_month.median()
    scale = median.mean()
    return pd.DataFrame({
        "percent": (median / scale - 1) * 100,
        "low": (by_month.quantile(0.25) / scale - 1) * 100,
        "high": (by_month.quantile(0.75) / scale - 1) * 100,
        "years_above": by_month.apply(lambda month: int((month > scale).sum())),
        "years": by_month.size(),
    })


def coming_dates(calendar: pd.DataFrame, event: str, last_day: pd.Timestamp) -> list:
    """The dates of `event` in progress or next, then the ones after, so the app can move on once they pass."""
    dates = calendar[calendar.event == event].sort_values("start")
    coming = dates[dates.end >= last_day]
    upcoming = coming.iloc[:2] if len(coming) else dates.iloc[-1:]
    return [{"start": f"{row.start:%Y-%m-%d}", "end": f"{row.end:%Y-%m-%d}"} for row in upcoming.itertuples()]


def evidence(event: festivals.Event, found: pd.Series, years: str) -> str:
    size = f"{abs(found.effect):.0f}%"
    if event.moves and found.verdict == "unclear":
        return f"No clear effect on prices in {years}."
    if event.moves:
        return f"Prices are usually about {size} {found.verdict} than normal for these dates."
    if found.verdict == "unclear":
        return "No steady effect on prices on these dates."
    side = "below" if found.verdict == "lower" else "above"
    return f"Prices on these dates are usually {size} {side} the yearly average."


def periods_json(zone: str, calendar: pd.DataFrame, effects: pd.DataFrame, last_day: pd.Timestamp,
                 years: str) -> list:
    """The zone's festivals and seasons in calendar order; North Indian ones only where they clearly move prices."""
    periods = []
    for event in festivals.EVENTS:
        if zone not in event.zones:
            continue
        found = effects.loc[(zone, event.id)]
        if "(North India)" in event.name and found.verdict == "unclear":
            continue
        periods.append({
            "id": event.id, "name": event.name, "effect": found.verdict, "datesShift": event.moves,
            "note": f"{event.note} {evidence(event, found, years)}",
            "dates": coming_dates(calendar, event.id, last_day),
        })
    # Calendar order from January; the app re-sorts by the dates that are coming.
    return sorted(periods, key=lambda period: period["dates"][0]["start"][5:])


def percent_json(value: float) -> float:
    return round(float(value), 1) + 0.0  # + 0.0 turns -0.0 into 0.0


def months_json(pattern: pd.DataFrame) -> list:
    return [
        {
            "month": int(month),
            "percent": percent_json(row.percent),
            "low": percent_json(row.low),
            "high": percent_json(row.high),
            "yearsAbove": int(row.years_above),
            "years": int(row.years),
        }
        for month, row in pattern.iterrows()
    ]


def app_payload(prices: pd.DataFrame | None = None) -> dict:
    """The app's month pattern file; `prices` by day with columns by zone id, all NECC prices by default."""
    prices = zone_prices() if prices is None else prices
    monthly = complete_months(prices)
    ratio = ratio_to_trend(monthly)
    calendar = festivals.read_calendar()
    effects = pd.read_csv(EFFECTS_PATH).set_index(["zone", "event"])
    last_day = prices.index.max()
    years = f"{prices.index.min().year}–{last_day.year}"
    return {
        "method": METHOD,
        "firstMonth": f"{monthly.index[0]:%Y-%m}",
        "lastMonth": f"{monthly.index[-1]:%Y-%m}",
        "zones": [
            {
                "id": zone.id,
                "name": zone.name,
                "months": months_json(month_pattern(ratio[zone.id])),
                "periods": periods_json(zone.id, calendar, effects, last_day, years),
            }
            for zone in app_zones().itertuples()
        ],
    }


def check(payload: dict) -> None:
    """Refuses to write what the app can't show."""
    ids = [zone["id"] for zone in payload["zones"]]
    if ids != list(app_zones().id):
        raise ValueError(f"unexpected zones {ids}")
    for zone in payload["zones"]:
        months = [month["month"] for month in zone["months"]]
        if months != list(range(1, 13)):
            raise ValueError(f"{zone['id']}: months {months}")
        values = [month[key] for month in zone["months"] for key in ("percent", "low", "high")]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{zone['id']}: missing month values")
        if not all(period["dates"] for period in zone["periods"]):
            raise ValueError(f"{zone['id']}: a festival without dates")


def write_payload(payload: dict, path=PATTERN_PATH) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
