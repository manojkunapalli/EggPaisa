#!/usr/bin/env python3
"""Phase 9 daily job: the latest NECC prices -> 14-day forecasts -> Public/forecast.json for the app.

    python3 Pipeline/forecast.py                   # read NECC's new prices, then forecast
    python3 Pipeline/forecast.py --skip-update     # forecast from the prices already in Data/
    python3 Pipeline/forecast.py --ca-file x.pem   # extra root certificate for NECC's site, passed to necc.py

The boosting model from Analysis/models.py (Phase 8) is refitted on every price known today. Each day's most likely
₹10 and ₹20 ranges, and their chances, come from how its forecasts turned out over the past year.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Analysis"))  # the Phase 6–8 modules

import festivals
import models
from backtest import HORIZONS
from eggdata import app_zones, daily_prices, zone_prices

OUTPUT = ROOT / "Public" / "forecast.json"
IST = ZoneInfo("Asia/Kolkata")
# Sizing today's ranges takes a year of past forecasts, and checking their chances takes the year before.
HISTORY_DAYS = 2 * 365 + 2 * max(HORIZONS)
# As in the app, a day NECC leaves blank takes the previous day's price.
FILL_DAYS = 7


def update_prices(ca_file: str | None) -> None:
    command = [sys.executable, str(ROOT / "Scripts" / "necc.py"), "update"]
    if ca_file:
        command += ["--ca-file", ca_file]
    subprocess.run(command, check=True)


def forecast() -> dict:
    daily = daily_prices()
    published = zone_prices(daily)
    prices = published.ffill(limit=FILL_DAYS)
    flags = models.festival_flags(prices)
    rows = models.boosting_forecasts(daily, prices, flags, prices.index[-HISTORY_DAYS:])
    origin = prices.index[-1]
    ranged = {"range10": models.add_ranges(rows, steps=1), "range20": models.add_ranges(rows, steps=2)}
    ranges = {name: table[table.origin == origin].set_index(["zone", "h"]) for name, table in ranged.items()}
    zones = []
    for zone in app_zones().itertuples():
        today = ranges["range10"].loc[zone.id]
        zones.append({
            "id": zone.id,
            "name": zone.name,
            "price": _number(prices.at[origin, zone.id]),
            "priceDate": f"{published[zone.id].last_valid_index():%Y-%m-%d}",
            "days": [
                {
                    "date": f"{origin + pd.Timedelta(days=h):%Y-%m-%d}",
                    "forecast": round(float(today.at[h, "forecast"]), 1),
                    **{name: _range(table.loc[(zone.id, h)]) for name, table in ranges.items()},
                }
                for h in HORIZONS
            ],
        })
    return {
        "generated": datetime.now(IST).isoformat(timespec="seconds"),
        "origin": f"{origin:%Y-%m-%d}",
        "unit": "₹ per 100 eggs",
        "method": "Boosting model refitted on all NECC prices to the origin day. range10/range20: the most likely "
                  "₹10/₹20 range; chance: how often such ranges were right over the past year.",
        "zones": zones,
    }


def check(payload: dict) -> None:
    """Refuses to publish what the app can't use; the forecast already online stays."""
    ids = [zone["id"] for zone in payload["zones"]]
    if ids != list(app_zones().id):
        raise ValueError(f"unexpected zones {ids}")
    for zone in payload["zones"]:
        if len(zone["days"]) != len(HORIZONS):
            raise ValueError(f"{zone['id']}: {len(zone['days'])} days")
        for day in zone["days"]:
            ranges = [day["range10"], day["range20"]]
            # NaN fails every comparison, so missing values are caught too.
            ranges_ok = all(found["low"] < found["high"] and 0 <= found["chance"] <= 1 for found in ranges)
            if not (ranges_ok and math.isfinite(day["forecast"])):
                raise ValueError(f"{zone['id']} {day['date']}: {day}")


def summary(payload: dict) -> str:
    lines = [f"Forecast from NECC prices on {payload['origin']} (most likely ₹10 range, chance):"]
    for zone in payload["zones"]:
        first, last = zone["days"][0]["range10"], zone["days"][-1]["range10"]
        lines.append(
            f"  {zone['name']:<11} ₹{zone['price']:<6} next day {first['low']}–{first['high']} {first['chance']:.0%}"
            f", day 14 {last['low']}–{last['high']} {last['chance']:.0%}"
        )
    return "\n".join(lines)


def _range(row: pd.Series) -> dict:
    return {"low": _number(row.low), "high": _number(row.high), "chance": round(float(row.probability), 2)}


def _number(value: float) -> float | int:
    value = float(value)
    return int(value) if value.is_integer() else round(value, 2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NECC prices -> 14-day forecasts -> Public/forecast.json")
    parser.add_argument("--skip-update", action="store_true", help="use the prices in Data/ without reading NECC")
    parser.add_argument("--ca-file", help="extra root certificate (PEM) for NECC's site, e.g. a proxy's")
    args = parser.parse_args(argv)
    started = time.time()
    try:
        if not args.skip_update:
            update_prices(args.ca_file)
        festivals.ensure_calendar()
        payload = forecast()
        check(payload)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(summary(payload))
    print(f"Wrote {OUTPUT.relative_to(ROOT)} in {time.time() - started:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
