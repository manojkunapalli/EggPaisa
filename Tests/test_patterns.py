"""The monthly job: Analysis/high_months.py, Analysis/festival_effects.py and Pipeline/patterns.py."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

import Tests  # noqa: F401  (adds the project folders to the import path)

import festival_effects
import high_months
import patterns


def daily(first: str, last: str) -> pd.DataFrame:
    days = pd.date_range(first, last, freq="D")
    return pd.DataFrame({"chittoor": np.linspace(500, 600, len(days))}, index=days)


def calendar(event: str, *spans: tuple) -> pd.DataFrame:
    rows = [(event, pd.Timestamp(start).year, pd.Timestamp(start), pd.Timestamp(end)) for start, end in spans]
    return pd.DataFrame(rows, columns=["event", "year", "start", "end"])


class HighMonthsTests(unittest.TestCase):
    def test_current_month_waits_until_complete(self):
        self.assertEqual(high_months.complete_months(daily("2025-01-01", "2025-03-30")).index[-1],
                         pd.Timestamp("2025-02-01"))
        self.assertEqual(high_months.complete_months(daily("2025-01-01", "2025-03-31")).index[-1],
                         pd.Timestamp("2025-03-01"))

    def test_month_pattern(self):
        months = pd.date_range("2020-01-01", "2022-12-01", freq="MS")
        ratio = pd.Series(np.where(months.month == 11, 1.12, 1.0), index=months)
        pattern = high_months.month_pattern(ratio)
        self.assertEqual(list(pattern.index), list(range(1, 13)))
        self.assertEqual(pattern.percent.idxmax(), 11)
        self.assertAlmostEqual(pattern.percent.mean(), 0)
        self.assertEqual(pattern.at[11, "years_above"], 3)
        self.assertEqual(pattern.at[5, "years_above"], 0)
        self.assertEqual(pattern.at[11, "years"], 3)

    def test_coming_dates_are_current_or_next_then_the_one_after(self):
        dates = calendar("sawan", ("2025-07-11", "2025-08-09"), ("2026-07-30", "2026-08-28"),
                         ("2027-07-19", "2027-08-17"))
        during = high_months.coming_dates(dates, "sawan", pd.Timestamp("2026-08-01"))
        self.assertEqual(during, [{"start": "2026-07-30", "end": "2026-08-28"},
                                  {"start": "2027-07-19", "end": "2027-08-17"}])
        after_all = high_months.coming_dates(dates, "sawan", pd.Timestamp("2027-09-01"))
        self.assertEqual(after_all, [{"start": "2027-07-19", "end": "2027-08-17"}])

    def test_percent_has_no_negative_zero(self):
        self.assertEqual(json.dumps(high_months.percent_json(-0.04)), "0.0")
        self.assertEqual(high_months.percent_json(12.345), 12.3)

    def test_check_refuses_a_missing_month(self):
        payload = json.loads(high_months.PATTERN_PATH.read_text(encoding="utf-8"))
        high_months.check(payload)
        payload["zones"][0]["months"].pop()
        with self.assertRaises(ValueError):
            high_months.check(payload)


class FestivalEffectTests(unittest.TestCase):
    def verdict(self, **row) -> str:
        values = {"kind": "moves", "event": "sawan", "effect": -3.0, "p": 0.01, "same_sign": np.nan}
        return festival_effects.verdict(pd.Series({**values, **row}))

    def test_verdicts(self):
        self.assertEqual(self.verdict(), "lower")
        self.assertEqual(self.verdict(p=0.2), "unclear")
        self.assertEqual(self.verdict(effect=-0.5), "unclear")
        # Sawan lowering demand is expected; higher prices then are taken as chance.
        self.assertEqual(self.verdict(effect=3.0), "unclear")
        self.assertEqual(self.verdict(kind="fixed", event="winter", effect=5.0, same_sign=0.8), "higher")
        self.assertEqual(self.verdict(kind="fixed", event="winter", effect=5.0, same_sign=0.5), "unclear")

    def test_days_before_and_after(self):
        days = pd.date_range("2026-01-01", "2026-01-31", freq="D")
        dates = calendar("sankranti", ("2026-01-13", "2026-01-16"))
        before = festival_effects.nearby(dates, "sankranti", days, before=True, width=3)
        after = festival_effects.nearby(dates, "sankranti", days, before=False, width=3)
        self.assertEqual(list(before[before].index.day), [10, 11, 12])
        self.assertEqual(list(after[after].index.day), [17, 18, 19])

    def test_level_is_percent_of_the_yearly_average(self):
        days = pd.date_range("2024-01-01", "2025-12-31", freq="D")
        prices = pd.DataFrame({"chittoor": 600.0}, index=days)
        prices.loc["2024-11-01":"2024-11-30"] = 660.0
        level = festival_effects.price_level(prices)
        self.assertGreater(level.at[pd.Timestamp("2024-11-15"), "chittoor"], 8)
        self.assertTrue(level.chittoor.iloc[:100].isna().all())


class MonthlyJobTests(unittest.TestCase):
    def test_reads_the_last_month_of_the_app_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pattern.json"
            self.assertIsNone(patterns.published_month(path))
            path.write_text('{"lastMonth": "2026-09"}', encoding="utf-8")
            self.assertEqual(patterns.published_month(path), "2026-09")

    def test_does_nothing_until_a_new_month_is_complete(self):
        prices = daily("2025-01-01", "2026-10-27")
        with mock.patch.object(patterns, "zone_prices", return_value=prices), \
                mock.patch.object(patterns, "published_month", return_value="2026-09"), \
                mock.patch.object(patterns.festival_effects, "write_effects") as write_effects, \
                mock.patch.object(patterns.high_months, "write_payload") as write_payload, \
                mock.patch("builtins.print"):
            self.assertEqual(patterns.main([]), 0)
        write_effects.assert_not_called()
        write_payload.assert_not_called()
