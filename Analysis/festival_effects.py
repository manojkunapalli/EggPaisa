"""Phase 6: what each festival or season does to each zone's NECC price -> Data/festival_effects.csv.

Festivals whose dates move: a regression of the price level on the festival days, with week-of-year and shock
controls, all of a zone's festivals together. Seasons on the same dates every year can't be told apart from the
yearly pattern, so for those it's the usual price level on their dates. events.ipynb shows the results.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

import festivals
from eggdata import DATA

EFFECTS_PATH = DATA / "festival_effects.csv"
# Set aside, so they don't count as festival effects.
SHOCKS = {"COVID-19": ("2020-02-01", "2020-05-31"), "bird flu 2021": ("2021-01-04", "2021-02-28")}
COLUMNS = ["zone", "event", "kind", "effect", "low", "high", "p", "before", "after", "same_sign", "years", "verdict"]


def price_level(prices: pd.DataFrame) -> pd.DataFrame:
    """Each day's price as % above or below the yearly average around it (a centred 365-day average)."""
    return 100 * (prices / prices.rolling(365, center=True, min_periods=300).mean() - 1)


def week_of_year(days: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(np.minimum((days.dayofyear - 1) // 7, 51), index=days)


def control_columns(days: pd.DatetimeIndex) -> pd.DataFrame:
    """Week-of-year dummies plus one column per shock."""
    shocks = pd.DataFrame(
        {name: ((days >= start) & (days <= end)).astype(float) for name, (start, end) in SHOCKS.items()},
        index=days,
    )
    return pd.get_dummies(week_of_year(days), prefix="week", drop_first=True, dtype=float).join(shocks)


def moving_events(zone: str) -> list:
    return [event.id for event in festivals.EVENTS if event.moves and zone in event.zones]


def nearby(calendar: pd.DataFrame, event: str, days: pd.DatetimeIndex, before: bool, width: int = 14) -> pd.Series:
    """True in the `width` days before (or after) each occurrence of `event`."""
    marked = pd.Series(False, index=days)
    for row in calendar[calendar.event == event].itertuples():
        if before:
            marked.loc[row.start - pd.Timedelta(days=width):row.start - pd.Timedelta(days=1)] = True
        else:
            marked.loc[row.end + pd.Timedelta(days=1):row.end + pd.Timedelta(days=width)] = True
    return marked


def fit(level: pd.Series, controls: pd.DataFrame, regressors: pd.DataFrame):
    """Price level on the controls plus `regressors`, with errors allowing for slow drift."""
    data = sm.add_constant(controls.join(regressors.astype(float)))
    known = level.notna()
    return sm.OLS(level[known], data[known]).fit(cov_type="HAC", cov_kwds={"maxlags": 60})


def during_effects(level: pd.DataFrame, controls: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    """Each moving festival's effect with its 95% range and p-value; a zone's festivals are fitted together."""
    rows = []
    for zone in level.columns:
        events = moving_events(zone)
        result = fit(level[zone], controls, flags[events])
        interval = result.conf_int()
        rows += [{"zone": zone, "event": event, "effect": result.params[event], "low": interval.loc[event, 0],
                  "high": interval.loc[event, 1], "p": result.pvalues[event]} for event in events]
    return pd.DataFrame(rows)


def around_effects(level: pd.DataFrame, controls: pd.DataFrame, flags: pd.DataFrame,
                   calendar: pd.DataFrame) -> pd.DataFrame:
    """The 14 days before, during and 14 days after each moving festival, one festival at a time."""
    rows = []
    for zone in level.columns:
        for event in moving_events(zone):
            parts = pd.DataFrame({"before": nearby(calendar, event, level.index, before=True), "during": flags[event],
                                  "after": nearby(calendar, event, level.index, before=False)})
            rows.append({"zone": zone, "event": event,
                         **fit(level[zone], controls, parts).params[["before", "during", "after"]]})
    return pd.DataFrame(rows)


def fixed_effects(level: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Seasons on the same dates every year: the median price level on their dates across years."""
    rows = []
    for event in [event for event in festivals.EVENTS if not event.moves]:
        occurrences = calendar[calendar.event == event.id]
        for zone in event.zones:
            levels = pd.Series([level[zone].loc[row.start:row.end].mean()
                                for row in occurrences.itertuples()]).dropna()
            median = levels.median()
            rows.append({"zone": zone, "event": event.id, "effect": median, "years": len(levels),
                         "same_sign": (np.sign(levels) == np.sign(median)).mean()})
    return pd.DataFrame(rows)


def verdict(row: pd.Series) -> str:
    """Lower or higher when the effect is clear, otherwise unclear."""
    if row.kind == "moves":
        clear = row.p < 0.05 and abs(row.effect) >= 1
    else:
        clear = abs(row.effect) >= 2 and row.same_sign >= 0.7
    found = "lower" if row.effect < 0 else "higher"
    # A dated festival moving prices the opposite way to what people expect is treated as chance.
    if not clear or (row.kind == "moves" and found != festivals.EVENTS_BY_ID[row.event].expected):
        return "unclear"
    return found


def combine(during: pd.DataFrame, around: pd.DataFrame, fixed: pd.DataFrame) -> pd.DataFrame:
    effects = pd.concat([during.assign(kind="moves"), fixed.assign(kind="fixed")], ignore_index=True)
    effects = effects.join(around.set_index(["zone", "event"])[["before", "after"]], on=["zone", "event"])
    effects["verdict"] = effects.apply(verdict, axis=1)
    return effects[COLUMNS]


def festival_effects(prices: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Every zone's festivals and seasons with their effect and verdict; `prices` by day, columns by zone id."""
    level = price_level(prices)
    controls = control_columns(prices.index)
    flags = festivals.daily_flags(prices.index, calendar)
    during = during_effects(level, controls, flags)
    return combine(during, around_effects(level, controls, flags, calendar), fixed_effects(level, calendar))


def write_effects(effects: pd.DataFrame, path=EFFECTS_PATH) -> None:
    effects[COLUMNS].round(3).to_csv(path, index=False, lineterminator="\n")
