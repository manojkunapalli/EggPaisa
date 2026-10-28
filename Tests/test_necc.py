"""Scripts/necc.py: reading NECC's monthly sheet and writing the app's price file."""
import datetime as dt
import json
import unittest

from Tests import FIXTURES

import necc

OCTOBER = (FIXTURES / "necc_daily_2026_10.html").read_text(encoding="utf-8")
TODAY = dt.date(2026, 10, 27)
CHITTOOR_DAY_1 = "<td align='left'>Chittoor</td><td>593</td>"


def find(zones: list, name: str) -> necc.ZoneMonth:
    return next(zone for zone in zones if zone.zone == name)


class ParseSheetTests(unittest.TestCase):
    def test_reads_every_zone_in_both_sections(self):
        zones = necc.parse_sheet(OCTOBER, 2026, 10, TODAY)
        self.assertEqual(len(zones), 34)
        self.assertEqual(sum(zone.kind == "suggested" for zone in zones), 24)
        self.assertEqual(sum(zone.kind == "prevailing" for zone in zones), 10)

    def test_reads_prices_and_average(self):
        zones = necc.parse_sheet(OCTOBER, 2026, 10, TODAY)
        chittoor = find(zones, "Chittoor")
        self.assertEqual(chittoor.kind, "suggested")
        self.assertEqual(chittoor.prices[dt.date(2026, 10, 1)], 593)
        self.assertEqual(chittoor.prices[dt.date(2026, 10, 27)], 633)
        self.assertEqual(chittoor.average, 607.26)
        self.assertEqual(find(zones, "Hyderabad").prices[dt.date(2026, 10, 24)], 570)
        self.assertEqual(find(zones, "Kolkata (WB)").prices[dt.date(2026, 10, 27)], 645)

    def test_keeps_only_days_up_to_today(self):
        zones = necc.parse_sheet(OCTOBER, 2026, 10, dt.date(2026, 10, 10))
        self.assertEqual(max(max(zone.prices) for zone in zones if zone.prices), dt.date(2026, 10, 10))

    def test_dash_is_no_price(self):
        html = OCTOBER.replace(CHITTOOR_DAY_1, "<td align='left'>Chittoor</td><td>-</td>", 1)
        zones = necc.parse_sheet(html, 2026, 10, TODAY)
        self.assertIsNone(find(zones, "Chittoor").prices[dt.date(2026, 10, 1)])
        rows = necc.sheet_rows(zones)
        self.assertNotIn((dt.date(2026, 10, 1), "Chittoor"), rows)
        self.assertEqual(rows[(dt.date(2026, 10, 2), "Chittoor")], ("suggested", 593))

    def test_refuses_another_month(self):
        with self.assertRaisesRegex(ValueError, "asked for 2026-09"):
            necc.parse_sheet(OCTOBER, 2026, 9, TODAY)

    def test_refuses_unreadable_price(self):
        html = OCTOBER.replace(CHITTOOR_DAY_1, "<td align='left'>Chittoor</td><td>59x</td>", 1)
        with self.assertRaisesRegex(ValueError, "Chittoor"):
            necc.parse_sheet(html, 2026, 10, TODAY)

    def test_month_without_table_has_no_prices(self):
        start = OCTOBER.index("Name Of Zone")
        html = OCTOBER[:start] + OCTOBER[start:].replace("Name Of Zone", "Nothing here", 1)
        self.assertEqual(necc.parse_sheet(html, 2026, 10, TODAY), [])

    def test_price_text(self):
        self.assertEqual(necc._price("1,234"), 1234)
        self.assertIsNone(necc._price("-"))
        self.assertIsNone(necc._price(""))

    def test_page_shows_the_clarification(self):
        self.assertIn(necc.CLARIFICATION, " ".join(OCTOBER.split()))


class AppFileTests(unittest.TestCase):
    def test_missing_day_is_null(self):
        rows = {}
        for _, _, necc_name in necc.APP_ZONES:
            rows[(dt.date(2026, 10, 1), necc_name)] = ("suggested", 600.0)
            rows[(dt.date(2026, 10, 3), necc_name)] = ("suggested", 610.5)
        payload = necc.app_payload(rows)
        self.assertEqual([zone["id"] for zone in payload["zones"]], [zone[0] for zone in necc.APP_ZONES])
        self.assertEqual(payload["lastPriceDate"], "2026-10-03")
        chittoor = payload["zones"][0]
        self.assertEqual(chittoor["start"], "2026-10-01")
        self.assertEqual(chittoor["prices"], [600, None, 610.5])

    def test_refuses_a_zone_without_prices(self):
        with self.assertRaisesRegex(ValueError, "no prices"):
            necc.app_payload({(dt.date(2026, 10, 1), "Chittoor"): ("suggested", 600.0)})

    def test_app_file_matches_the_csv(self):
        expected = json.dumps(necc.app_payload(necc.read_csv()), ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(necc.APP_JSON_PATH.read_text(encoding="utf-8"), expected + "\n")
