"""Pipeline/forecast.py: what the daily job publishes for the app, and what it refuses to publish."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

import Tests  # noqa: F401  (adds the project folders to the import path)

import forecast
from backtest import HORIZONS
from eggdata import app_zones

ORIGIN = pd.Timestamp("2026-10-27")


def good_payload() -> dict:
    """Shaped like forecast.forecast()'s output."""
    zones = []
    for zone in app_zones().itertuples():
        days = [
            {
                "date": f"{ORIGIN + pd.Timedelta(days=h):%Y-%m-%d}",
                "forecast": 600.0,
                "range10": {"low": 595, "high": 605, "chance": 0.6},
                "range20": {"low": 590, "high": 610, "chance": 0.8},
            }
            for h in HORIZONS
        ]
        zones.append({"id": zone.id, "name": zone.name, "price": 600, "priceDate": "2026-10-27", "days": days})
    return {"generated": "2026-10-27T20:17:15+05:30", "origin": "2026-10-27", "zones": zones}


class CheckTests(unittest.TestCase):
    def test_accepts_a_good_forecast(self):
        forecast.check(good_payload())

    def assert_refused(self, change) -> None:
        payload = copy.deepcopy(good_payload())
        change(payload)
        with self.assertRaises(ValueError):
            forecast.check(payload)

    def test_refuses_a_missing_zone(self):
        self.assert_refused(lambda payload: payload["zones"].pop())

    def test_refuses_zones_out_of_order(self):
        self.assert_refused(lambda payload: payload["zones"].reverse())

    def test_refuses_a_missing_day(self):
        self.assert_refused(lambda payload: payload["zones"][0]["days"].pop())

    def test_refuses_an_empty_range(self):
        self.assert_refused(lambda payload: payload["zones"][1]["days"][3]["range10"].update(high=595))

    def test_refuses_a_chance_above_one(self):
        self.assert_refused(lambda payload: payload["zones"][2]["days"][0]["range20"].update(chance=1.5))

    def test_refuses_missing_numbers(self):
        self.assert_refused(lambda payload: payload["zones"][3]["days"][5].update(forecast=math.nan))
        self.assert_refused(lambda payload: payload["zones"][3]["days"][5]["range10"].update(low=math.nan))


class FormatTests(unittest.TestCase):
    def test_whole_prices_are_integers(self):
        self.assertEqual(forecast._number(633.0), 633)
        self.assertIsInstance(forecast._number(633.0), int)
        self.assertEqual(forecast._number(612.3456), 612.35)

    def test_range(self):
        row = pd.Series({"low": 630.0, "high": 640.0, "probability": 0.6789})
        self.assertEqual(forecast._range(row), {"low": 630, "high": 640, "chance": 0.68})

    def test_summary_lists_every_zone(self):
        text = forecast.summary(good_payload())
        for name in app_zones().name:
            self.assertIn(name, text)


class MainTests(unittest.TestCase):
    """The job writes Public/forecast.json only when the forecast passes the check."""

    def run_main(self, payload: dict) -> tuple:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "forecast.json"
            with mock.patch.object(forecast, "ROOT", Path(folder)), \
                    mock.patch.object(forecast, "OUTPUT", output), \
                    mock.patch.object(forecast.festivals, "ensure_calendar"), \
                    mock.patch.object(forecast, "forecast", return_value=payload), \
                    mock.patch("builtins.print"):
                status = forecast.main(["--skip-update"])
            written = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
        return status, written

    def test_publishes_a_good_forecast(self):
        status, written = self.run_main(good_payload())
        self.assertEqual(status, 0)
        self.assertEqual(written, good_payload())

    def test_keeps_the_old_forecast_when_the_check_fails(self):
        payload = good_payload()
        payload["zones"].pop()
        status, written = self.run_main(payload)
        self.assertEqual(status, 1)
        self.assertIsNone(written)
