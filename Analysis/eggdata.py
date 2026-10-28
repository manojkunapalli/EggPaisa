"""Shared loaders for the analysis notebooks."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data"
RESOURCES = ROOT / "EggPaisa" / "Resources"


def app_zones() -> pd.DataFrame:
    """The app's zones in display order: id, name and neccName."""
    file = json.loads((RESOURCES / "necc_prices.json").read_text(encoding="utf-8"))
    return pd.DataFrame(file["zones"])[["id", "name", "neccName"]]


def daily_prices() -> pd.DataFrame:
    """Every NECC zone by day, columns named as on the NECC sheet.

    A missing day takes the previous day's price; nothing is filled before a zone's first or after its latest price.
    """
    rows = pd.read_csv(DATA / "necc_daily.csv", parse_dates=["date"])
    published = rows.pivot(index="date", columns="zone", values="price")
    days = pd.date_range(published.index.min(), published.index.max(), freq="D")
    return published.reindex(days).ffill(limit_area="inside")


def zone_prices(daily: pd.DataFrame | None = None) -> pd.DataFrame:
    """The 7 app zones by day, columns named by zone id."""
    daily = daily_prices() if daily is None else daily
    zones = app_zones()
    return daily[list(zones.neccName)].set_axis(list(zones.id), axis=1)
