"""Phase 8 models for 14-day forecasts, and the most likely ₹10 range with its probability.

- boosting: one gradient-boosted tree model per day ahead, trained on all 7 zones, predicting the % change from today's
  price (scikit-learn's HistGradientBoosting, the same kind of model as LightGBM)
- arima: per zone, ARIMA(1,1,1) on log prices with yearly sine/cosine terms and festival markers

Both are refitted every six months using only prices known on the refit day.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from statsmodels.tsa.statespace.sarimax import SARIMAX

from backtest import HORIZONS, STEP, YEARS_BACK
from festivals import EVENTS, daily_flags, read_calendar

MOVING = tuple(event for event in EVENTS if event.moves)
CHANGE_DAYS = (1, 2, 3, 5, 7, 14, 21, 28, 56, 91)
# Zones that often move first (Phase 4), by NECC name.
LEADERS = ("Namakkal", "Hyderabad", "Kolkata (WB)", "E.Godavari", "Barwala")
REFIT_DAYS = 182
BOOSTING_SETTINGS = dict(
    loss="absolute_error", learning_rate=0.07, max_iter=200, max_leaf_nodes=31, min_samples_leaf=100,
    l2_regularization=1.0, random_state=0,
)


def festival_flags(prices: pd.DataFrame) -> pd.DataFrame:
    """Festival flags up to 14 days past the latest price; festival dates are known ahead."""
    days = pd.date_range(prices.index[0], prices.index[-1] + pd.Timedelta(days=max(HORIZONS)))
    return daily_flags(days, read_calendar())


def _relevant_flags(flags: pd.DataFrame, zone: str) -> pd.DataFrame:
    """Moving-festival flags, switched off where the festival doesn't apply to `zone`."""
    return pd.DataFrame({event.id: flags[event.id] & (zone in event.zones) for event in MOVING}).astype(float)


def _refit_days(days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Every REFIT_DAYS counted back from the last day, so the latest forecasts use the newest model."""
    refits = days[::-1][::REFIT_DAYS][::-1]
    return refits if refits[0] == days[0] else refits.insert(0, days[0])


def base_features(daily: pd.DataFrame, prices: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    """Features known on each origin day, the same for every day ahead; rows indexed by (origin, zone)."""
    log = 100 * np.log(prices)
    leaders = 100 * np.log(daily[list(LEADERS)])
    shared = {}
    for name in LEADERS:
        shared[f"{name} 1d"] = leaders[name] - leaders[name].shift(1)
        shared[f"{name} 3d"] = leaders[name] - leaders[name].shift(3)
    shared = pd.DataFrame(shared).reindex(prices.index)
    day_of_year = 2 * np.pi * prices.index.dayofyear / 365.25
    frames = []
    for code, zone in enumerate(prices.columns):
        series = log[zone]
        changed = series.diff().fillna(0).ne(0)
        frame = pd.DataFrame({f"change {days}d": series - series.shift(days) for days in CHANGE_DAYS})
        frame["days since change"] = series.groupby(changed.cumsum()).cumcount()
        frame["last change"] = series.diff().where(changed).ffill()
        frame["vs 365-day average"] = 100 * (prices[zone] / prices[zone].rolling(365, min_periods=300).mean() - 1)
        frame["vs last year"] = series - series.shift(365)
        frame["season sin"], frame["season cos"] = np.sin(day_of_year), np.cos(day_of_year)
        frame = frame.join(shared).join(_relevant_flags(flags, zone).add_prefix("in ").reindex(prices.index))
        frames.append(frame.assign(zone=code, origin=prices.index, zone_id=zone))
    return pd.concat(frames).set_index(["origin", "zone_id"])


def horizon_features(base: pd.DataFrame, prices: pd.DataFrame, flags: pd.DataFrame, h: int) -> pd.DataFrame:
    """`base` plus features for the `h` days ahead: past years' changes and festival days coming up."""
    log = 100 * np.log(prices)
    changes = [log.shift(365 * year - h) - log.shift(365 * year) for year in range(1, YEARS_BACK + 1)]
    extra = []
    for zone in prices.columns:
        coming = _relevant_flags(flags, zone).rolling(h).mean().shift(-h).reindex(prices.index)
        frame = coming.add_prefix("coming ").assign(
            **{"last year's change": changes[0][zone],
               "5-year average change": pd.concat([change[zone] for change in changes], axis=1).mean(axis=1)}
        )
        extra.append(frame.assign(origin=prices.index, zone_id=zone))
    return base.join(pd.concat(extra).set_index(["origin", "zone_id"]))


def change_target(prices: pd.DataFrame, h: int, index: pd.MultiIndex) -> pd.Series:
    """% log change over the `h` days after each origin, aligned to (origin, zone_id) `index`."""
    log = 100 * np.log(prices)
    return (log.shift(-h) - log).stack(future_stack=True).rename_axis(["origin", "zone_id"]).reindex(index)


def training_rows(index: pd.MultiIndex, target: pd.Series, prices: pd.DataFrame, refit_day: pd.Timestamp,
                  h: int) -> np.ndarray:
    """Rows whose outcome was known on `refit_day`, after a first year that lacks yearly features."""
    origin = index.get_level_values("origin")
    return (origin <= refit_day - pd.Timedelta(days=h)) & (origin >= prices.index[0] + pd.Timedelta(days=365)) \
        & target.notna().to_numpy()


def boosting_forecasts(daily: pd.DataFrame, prices: pd.DataFrame, flags: pd.DataFrame,
                       days: pd.DatetimeIndex) -> pd.DataFrame:
    """Forecast rows for every origin in `days`, refitting every six months."""
    base = base_features(daily, prices, flags)
    refits = _refit_days(days)
    rows = []
    for h in HORIZONS:
        features = horizon_features(base, prices, flags, h)
        target = change_target(prices, h, features.index)
        origin = features.index.get_level_values("origin")
        zone_column = list(features.columns).index("zone")
        for start, stop in zip(refits, [*refits[1:], days[-1] + pd.Timedelta(days=1)]):
            train = training_rows(features.index, target, prices, start, h)
            model = HistGradientBoostingRegressor(**BOOSTING_SETTINGS, categorical_features=[zone_column])
            model.fit(features[train], target[train])
            chosen = (origin >= start) & (origin < stop)
            predicted = pd.Series(model.predict(features[chosen]), index=features.index[chosen])
            rows.append(predicted.rename("change").reset_index().assign(h=h))
    return _to_forecast_rows(pd.concat(rows), prices)


def _yearly_terms(index: pd.DatetimeIndex, harmonics: int = 3) -> pd.DataFrame:
    angle = 2 * np.pi * index.dayofyear / 365.25
    terms = {}
    for k in range(1, harmonics + 1):
        terms[f"sin {k}"], terms[f"cos {k}"] = np.sin(k * angle), np.cos(k * angle)
    return pd.DataFrame(terms, index=index)


def arima_forecasts(prices: pd.DataFrame, flags: pd.DataFrame, days: pd.DatetimeIndex,
                    train_days: int = 3 * 365) -> pd.DataFrame:
    """Forecast rows for every origin in `days`; each refit uses the previous `train_days` days."""
    index = pd.date_range(prices.index[0], prices.index[-1] + pd.Timedelta(days=max(HORIZONS)))
    refits = _refit_days(days)
    rows = []
    for zone in prices.columns:
        log = 100 * np.log(prices[zone]).reindex(index)
        exog = _yearly_terms(index).join(_relevant_flags(flags.reindex(index, fill_value=False), zone))
        exog = exog.loc[:, exog.loc[days[0] - pd.Timedelta(days=train_days):].std() > 0]
        for start, stop in zip(refits, [*refits[1:], days[-1] + pd.Timedelta(days=1)]):
            window = slice(start - pd.Timedelta(days=train_days), start)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = SARIMAX(log[window], exog=exog[window], order=(1, 1, 1)).fit(disp=False)
                for origin in days[(days >= start) & (days < stop)]:
                    if origin > start:
                        result = result.extend(log[origin:origin], exog=exog[origin:origin])
                    ahead = exog[origin + pd.Timedelta(days=1):origin + pd.Timedelta(days=max(HORIZONS))]
                    predicted = np.asarray(result.forecast(steps=max(HORIZONS), exog=ahead))
                    rows.append(pd.DataFrame({
                        "origin": origin, "zone_id": zone, "h": list(HORIZONS),
                        "change": predicted - log[origin],
                    }))
    return _to_forecast_rows(pd.concat(rows), prices)


def _to_forecast_rows(changes: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Predicted % log changes -> forecast rows with price and actual."""
    rows = changes.rename(columns={"zone_id": "zone"})
    price = prices.stack(future_stack=True).rename_axis(["origin", "zone"]).rename("price")
    rows = rows.join(price, on=["origin", "zone"])
    actual = [prices.shift(-h).stack(future_stack=True).rename_axis(["origin", "zone"]).rename(h) for h in HORIZONS]
    actual = pd.concat(actual, axis=1).rename_axis(columns="h").stack(future_stack=True).rename("actual")
    rows = rows.join(actual, on=["origin", "zone", "h"])
    rows["forecast"] = rows.price * np.exp(rows.change / 100)
    return rows[["zone", "origin", "h", "price", "forecast", "actual"]].reset_index(drop=True)


def combine(*models: pd.DataFrame) -> pd.DataFrame:
    """Average forecast (in log terms) of models that share the same rows."""
    keys = ["zone", "origin", "h"]
    logs = pd.concat([np.log(model.set_index(keys).forecast) for model in models], axis=1).mean(axis=1)
    first = models[0].set_index(keys)
    return first.assign(forecast=np.exp(logs.reindex(first.index))).reset_index()


def add_ranges(rows: pd.DataFrame, steps: int = 1, window_days: int = 365,
               width: float = 3.0, floor: float = 0.5) -> pd.DataFrame:
    """The most likely range of `2 * steps + 1` ₹5 steps (₹10 for 1) and its probability.

    The possible moves are the actual ₹5-step moves that followed this model's forecasts over the previous
    `window_days`, for the same zone and days ahead, weighted towards forecasts that predicted a similar % move
    (`width`, with `floor` keeping every past move in play). Only outcomes known on the origin day are used.
    """
    parts = []
    for (_, h), group in rows.groupby(["zone", "h"]):
        group = group.sort_values("origin")
        dates = group.origin.to_numpy()
        price, forecast = group.price.to_numpy(), group.forecast.to_numpy()
        predicted_move = 100 * np.log(forecast / price)
        actual_steps = np.round((group.actual.to_numpy() - price) / STEP)
        newest = np.searchsorted(dates, dates - np.timedelta64(h, "D"), side="right")
        oldest = np.searchsorted(dates, dates - np.timedelta64(h + window_days, "D"), side="right")
        low, high, probability = (np.full(len(group), np.nan) for _ in range(3))
        for i in range(len(group)):
            past = slice(oldest[i], newest[i])
            known = ~np.isnan(actual_steps[past])
            if known.sum() < window_days // 2:
                continue
            moves = actual_steps[past][known].astype(int)
            weights = np.exp(-0.5 * ((predicted_move[past][known] - predicted_move[i]) / width) ** 2) + floor
            counts = np.bincount(moves - moves.min(), weights=weights)
            # window[j] sums the weights within `steps` of step moves.min() + j.
            window = np.convolve(counts, np.ones(2 * steps + 1), mode="full")[steps:]
            centres = np.arange(len(window)) + moves.min()
            # Equal weights go to the range nearest the forecast.
            best = np.argmax(window - 1e-9 * np.abs(centres - (forecast[i] - price[i]) / STEP))
            low[i] = price[i] + STEP * (centres[best] - steps)
            high[i] = price[i] + STEP * (centres[best] + steps)
            probability[i] = window[best] / weights.sum()
        parts.append(group.assign(low=low, high=high, probability=probability))
    ranged = _recalibrate(pd.concat(parts), window_days)
    return ranged.sort_values(["origin", "zone", "h"]).reset_index(drop=True)


def _recalibrate(rows: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Scale each probability by how often ranges for the same days ahead were right over the previous year.

    Picking the best of many ranges overstates its chance; this uses only outcomes known on the origin day.
    """
    known = rows.actual.notna() & rows.probability.notna()
    right = ((rows.actual >= rows.low) & (rows.actual <= rows.high) & known).astype(float)
    parts = []
    for h, group in rows.assign(right=right, stated=rows.probability.where(known, 0)).groupby("h"):
        by_day = group.groupby("origin")[["right", "stated"]].sum()
        dates = by_day.index.to_numpy()
        right_total = np.concatenate([[0], by_day.right.cumsum().to_numpy()])
        stated_total = np.concatenate([[0], by_day.stated.cumsum().to_numpy()])
        newest = np.searchsorted(dates, dates - np.timedelta64(h, "D"), side="right")
        oldest = np.searchsorted(dates, dates - np.timedelta64(h + window_days, "D"), side="right")
        stated = stated_total[newest] - stated_total[oldest]
        factor = np.where(stated >= 20, (right_total[newest] - right_total[oldest]) / np.maximum(stated, 1e-9), np.nan)
        factor = pd.Series(factor, index=by_day.index)
        parts.append(group.assign(probability=(group.probability * group.origin.map(factor)).clip(upper=0.99)))
    return pd.concat(parts).drop(columns=["right", "stated"])
