"""Testing 14-day forecasts on past data: forecast days, simple forecasts, ₹10 ranges and scores.

Forecasts are rows of zone, origin (the day the forecast is made, using prices up to that day), h (days ahead),
price (the price on the origin day), forecast, low/high (the range) and, when known, actual.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = tuple(range(1, 15))
STEP = 5.0  # NECC prices move in ₹5 steps
YEARS_BACK = 5


def origins(prices: pd.DataFrame, years: int = 3, warmup_years: int = 0) -> pd.DatetimeIndex:
    """Every day of the last `years` (plus `warmup_years` before them) whose 14-day outcome is known."""
    last_day = prices.index.max()
    first = last_day - pd.DateOffset(years=years + warmup_years) + pd.Timedelta(days=1)
    return prices.loc[first:last_day - pd.Timedelta(days=max(HORIZONS))].index


def to_rows(forecasts: dict, prices: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """{h: date × zone forecasts} for the given origin days -> forecast rows with price and actual."""
    frames = []
    for h, table in forecasts.items():
        frame = pd.DataFrame({
            "forecast": table.loc[days].stack(),
            "price": prices.loc[days].stack(),
            "actual": prices.shift(-h).loc[days].stack(),
        })
        frames.append(frame.rename_axis(["origin", "zone"]).reset_index().assign(h=h))
    return pd.concat(frames, ignore_index=True)[["zone", "origin", "h", "price", "forecast", "actual"]]


def simple_forecasts(prices: pd.DataFrame, days: pd.DatetimeIndex) -> dict:
    """The forecasts to beat, as forecast rows by name.

    - same price: the price stays as it is today
    - last year's change: today's price moved by last year's % change over the same days
    - 5-year average change: today's price moved by the average % change over the same days in the last 5 years
    """
    log = np.log(prices)
    same, last_year, average = {}, {}, {}
    for h in HORIZONS:
        changes = [log.shift(365 * year - h) - log.shift(365 * year) for year in range(1, YEARS_BACK + 1)]
        same[h] = prices
        last_year[h] = prices * np.exp(changes[0])
        average[h] = prices * np.exp(pd.concat(changes).groupby(level=0).mean())
    named = {"same price": same, "last year's change": last_year, "5-year average change": average}
    return {name: with_centred_range(to_rows(table, prices, days)) for name, table in named.items()}


def snap(price: pd.Series, value: pd.Series) -> pd.Series:
    """`value` moved to the nearest ₹5 step from `price`."""
    return price + STEP * np.round((value - price) / STEP)


def with_centred_range(rows: pd.DataFrame) -> pd.DataFrame:
    """A ₹10 range centred on the forecast, e.g. 545–555 for 550."""
    centre = snap(rows.price, rows.forecast)
    return rows.assign(low=centre - STEP, high=centre + STEP)


def score(rows: pd.DataFrame) -> pd.DataFrame:
    known = rows.dropna(subset=["actual"])
    return known.assign(
        error=known.forecast - known.actual,
        hit=(known.actual >= known.low) & (known.actual <= known.high),
    )


def by_horizon(scored: dict) -> pd.DataFrame:
    """Average error in ₹ and ₹10 range hit rate (%) for each forecast and day ahead."""
    columns = {}
    for name, rows in scored.items():
        grouped = rows.groupby("h")
        columns[(name, "error ₹")] = grouped.error.apply(lambda error: error.abs().mean())
        columns[(name, "hit %")] = grouped.hit.mean() * 100
    return pd.DataFrame(columns).rename_axis("days ahead")


def by_zone(scored: dict, measure: str, days_ahead: tuple = (1, 7, 14)) -> pd.DataFrame:
    """`measure` ("error ₹" or "hit %") by zone, for a few days ahead."""
    columns = {}
    for name, rows in scored.items():
        chosen = rows[rows.h.isin(days_ahead)]
        grouped = chosen.groupby(["zone", "h"])
        values = grouped.error.apply(lambda error: error.abs().mean()) if measure == "error ₹" \
            else grouped.hit.mean() * 100
        for h in days_ahead:
            columns[(name, f"{h} d")] = values.xs(h, level="h")
    return pd.DataFrame(columns)


def calibration(rows: pd.DataFrame, edges: tuple = (0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0)) -> pd.DataFrame:
    """Stated probability against how often the range was right, by probability band."""
    band = pd.cut(rows.probability, list(edges), include_lowest=True)
    grouped = rows.groupby(band, observed=True)
    return pd.DataFrame({
        "forecasts": grouped.size(),
        "stated %": grouped.probability.mean() * 100,
        "right %": grouped.hit.mean() * 100,
    }).rename_axis("stated probability")
