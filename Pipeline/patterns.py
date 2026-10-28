#!/usr/bin/env python3
"""Monthly job: festival effects and the High-price months data for the app, once a month of NECC prices is complete.

    python3 Pipeline/patterns.py           # only when NECC has a new complete month
    python3 Pipeline/patterns.py --force   # now

Run after Pipeline/forecast.py has read NECC's new prices. Writes Data/festival_effects.csv and
EggPaisa/Resources/necc_month_pattern.json, and rebuilds Data/festival_calendar.csv when a new year is needed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Analysis"))  # the Phase 5–6 modules

import festival_effects
import festivals
import high_months
from eggdata import zone_prices


def published_month(path: Path) -> str | None:
    """The last month in the High-price months file the app has now."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))["lastMonth"]
    except (OSError, ValueError, KeyError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Festival effects and High-price months, once a month")
    parser.add_argument("--force", action="store_true", help="rebuild even without a new complete month")
    args = parser.parse_args(argv)
    started = time.time()
    try:
        prices = zone_prices()
        newest = f"{high_months.complete_months(prices).index[-1]:%Y-%m}"
        if not args.force and published_month(high_months.PATTERN_PATH) == newest:
            print(f"High-price months already run to {newest}")
            return 0
        festivals.ensure_calendar()
        effects = festival_effects.festival_effects(prices, festivals.read_calendar())
        festival_effects.write_effects(effects)
        payload = high_months.app_payload(prices)
        high_months.check(payload)
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    high_months.write_payload(payload)
    clear = effects[effects.verdict != "unclear"]
    print(f"Festival effects: {len(clear)} of {len(effects)} clear; wrote "
          f"{festival_effects.EFFECTS_PATH.relative_to(ROOT)}")
    print(f"High-price months {payload['firstMonth']} to {payload['lastMonth']}; wrote "
          f"{high_months.PATTERN_PATH.relative_to(ROOT)} in {time.time() - started:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
