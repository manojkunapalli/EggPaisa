#!/usr/bin/env python3
"""NECC daily egg prices: download the monthly sheets and keep them as a tidy CSV.

Standard library only (Python 3.9+). Prices are ₹ per 100 eggs.

    python3 Scripts/necc.py backfill            # once: every month from 2009-01 to now
    python3 Scripts/necc.py backfill --refresh  # also re-download sheets already in Data/raw
    python3 Scripts/necc.py update              # daily: re-read recent months, update CSV and app prices
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

URL = "https://www.e2necc.com/home/eggprice"
USER_AGENT = "EggPaisa/0.1 (egg price research)"
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "Data" / "raw"
CSV_PATH = ROOT / "Data" / "necc_daily.csv"
REPORT_PATH = ROOT / "Data" / "necc_backfill_report.txt"
APP_JSON_PATH = ROOT / "EggPaisa" / "Resources" / "necc_prices.json"
IST = ZoneInfo("Asia/Kolkata")
KINDS = ("suggested", "prevailing")
REQUEST_GAP_SECONDS = 1.0
# Zones shown in the app, in display order: (id, display name, name on the NECC sheet).
APP_ZONES = (
    ("chittoor", "Chittoor", "Chittoor"),
    ("chennai", "Chennai", "Chennai (CC)"),
    ("bengaluru", "Bengaluru", "Bengaluru (CC)"),
    ("namakkal", "Namakkal", "Namakkal"),
    ("kolkata", "Kolkata", "Kolkata (WB)"),
    ("vijayawada", "Vijayawada", "Vijayawada"),
    ("hyderabad", "Hyderabad", "Hyderabad"),
)
# NECC requires anyone sharing its suggested prices to show this text with them.
CLARIFICATION = (
    "The daily egg prices suggested by NECC, on its official website or through any other medium "
    "(including verbal, print and digital media) are merely suggestive and not mandatory. "
    "The suggested prices are published solely for the reference and information of the trade and industry. "
    "NECC does not by itself or through any person enforce compliance or adherence with such suggested "
    "egg prices in any manner whatsoever."
)

Rows = dict[tuple[dt.date, str], tuple[str, float]]


@dataclass
class ZoneMonth:
    zone: str
    kind: str
    average: float | None
    # Every date up to today; None where the sheet shows "-".
    prices: dict[dt.date, float | None] = field(default_factory=dict)


class _SheetPage(HTMLParser):
    """Table rows tagged with their table, plus the selected dropdown values."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[int, list[str]]] = []
        self.selected: dict[str, str] = {}
        self._tables: list[int] = []
        self._table_count = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._select: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table_count += 1
            self._tables.append(self._table_count)
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
        elif tag == "select":
            self._select = dict(attrs).get("name")
        elif tag == "option" and self._select:
            values = dict(attrs)
            if "selected" in values:
                self.selected[self._select] = (values.get("value") or "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._tables:
            self._tables.pop()
        elif tag in ("td", "th") and self._cell is not None:
            if self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append((self._tables[-1] if self._tables else 0, self._row))
            self._row = None
        elif tag == "select":
            self._select = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def read_page(html: str, year: int, month: int) -> _SheetPage:
    page = _SheetPage()
    page.feed(html)
    page.close()
    shown = (page.selected.get("ddlYear"), page.selected.get("ddlMonth"))
    if shown != (str(year), f"{month:02d}"):
        raise ValueError(f"asked for {_label((year, month))} but the page shows {shown}")
    return page


def parse_sheet(html: str, year: int, month: int, today: dt.date) -> list[ZoneMonth]:
    """Zone rows of one daily sheet; empty when the month has no price table."""
    page = read_page(html, year, month)
    label = _label((year, month))
    start = next(
        (i for i, (_, cells) in enumerate(page.rows) if cells and cells[0].startswith("Name Of Zone")),
        None,
    )
    if start is None:
        return []
    table, header = page.rows[start]
    days = [int(cell) for cell in header[1:-1] if cell.isdigit()]
    if header[-1] != "Average" or days != list(range(1, len(header) - 1)):
        raise ValueError(f"{label}: unexpected header {header}")

    last_day = calendar.monthrange(year, month)[1]
    kind: str | None = KINDS[0]
    zones: list[ZoneMonth] = []
    for row_table, cells in page.rows[start + 1:]:
        if row_table != table or not cells:
            continue
        if len(cells) == 1:
            if cells[0]:
                kind = next((k for k in KINDS if k in cells[0].lower()), None)
                if kind is None:
                    raise ValueError(f"{label}: unknown section {cells[0]!r}")
            continue
        if len(cells) != len(header):
            raise ValueError(f"{label}: {cells[0]!r} has {len(cells)} cells, header has {len(header)}")
        try:
            zone = ZoneMonth(cells[0], kind, _price(cells[-1]))
            for day, text in zip(days, cells[1:-1]):
                price = _price(text)
                if day > last_day:
                    if price is not None:
                        raise ValueError(f"price on day {day}")
                    continue
                date = dt.date(year, month, day)
                if date <= today:
                    zone.prices[date] = price
        except ValueError as error:
            raise ValueError(f"{label} {cells[0]}: {error}") from None
        zones.append(zone)
    return zones


def fetch_sheet(year: int, month: int, context: ssl.SSLContext) -> str:
    form = urllib.parse.urlencode({
        "ddlMonth": f"{month:02d}",
        "ddlYear": str(year),
        "rblReportType": "DailyReport",
        "btnReport": "Get Sheet",
    }).encode("ascii")
    request = urllib.request.Request(URL, data=form, headers={"User-Agent": USER_AGENT})
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, context=context, timeout=60) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except OSError as error:
            if attempt == attempts:
                raise
            print(f"  {_label((year, month))}: {error}; retrying", file=sys.stderr, flush=True)
            time.sleep(5 * attempt)
    raise AssertionError("unreachable")


def ssl_context(ca_file: str | None) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if ca_file:
        # Adds to the default roots, so the same command works on and off the proxy.
        context.load_verify_locations(cafile=ca_file)
    return context


def sheet_rows(zones: list[ZoneMonth]) -> Rows:
    return {
        (date, zone.zone): (zone.kind, price)
        for zone in zones
        for date, price in zone.prices.items()
        if price is not None
    }


def read_csv() -> Rows:
    with CSV_PATH.open(newline="", encoding="utf-8") as file:
        return {
            (dt.date.fromisoformat(row["date"]), row["zone"]): (row["type"], float(row["price"]))
            for row in csv.DictReader(file)
        }


def write_csv(rows: Rows) -> None:
    ordered = sorted(rows.items(), key=lambda item: (item[0][0], KINDS.index(item[1][0]), item[0][1]))
    temporary = CSV_PATH.with_suffix(".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["date", "zone", "type", "price"])
        for (date, zone), (kind, price) in ordered:
            writer.writerow([date.isoformat(), zone, kind, f"{price:g}"])
    temporary.replace(CSV_PATH)


def app_payload(rows: Rows) -> dict:
    series: dict[str, dict[dt.date, float]] = defaultdict(dict)
    for (date, zone), (_, price) in rows.items():
        series[zone][date] = price
    zones = []
    last_dates = []
    for zone_id, name, necc_name in APP_ZONES:
        prices = series.get(necc_name)
        if not prices:
            raise ValueError(f"no prices for {necc_name}")
        first, last = min(prices), max(prices)
        last_dates.append(last)
        days = range((last - first).days + 1)
        zones.append({
            "id": zone_id,
            "name": name,
            "neccName": necc_name,
            "type": rows[(last, necc_name)][0],
            "start": first.isoformat(),
            # One entry per day; null where NECC showed "-" (the app then uses the previous day's price).
            "prices": [_json_number(prices.get(first + dt.timedelta(days=day))) for day in days],
        })
    return {
        "source": "National Egg Co-ordination Committee (NECC)",
        "sourceURL": URL,
        "unit": "₹ per 100 eggs",
        "lastPriceDate": max(last_dates).isoformat(),
        "clarification": CLARIFICATION,
        "zones": zones,
    }


def write_app_json(rows: Rows) -> bool:
    text = json.dumps(app_payload(rows), ensure_ascii=False, separators=(",", ":")) + "\n"
    if APP_JSON_PATH.exists() and APP_JSON_PATH.read_text(encoding="utf-8") == text:
        return False
    APP_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_JSON_PATH.write_text(text, encoding="utf-8")
    return True


def write_report(sheets: dict[tuple[int, int], list[ZoneMonth]], row_count: int) -> None:
    keys = sorted(sheets)
    latest = {zone.zone for zone in sheets[keys[-1]]}
    listed: set[str] = set()
    first: dict[str, dt.date] = {}
    last: dict[str, dt.date] = {}
    kinds: dict[str, set[str]] = defaultdict(set)
    per_year: dict[str, Counter[int]] = defaultdict(Counter)
    priced: dict[str, set[dt.date]] = defaultdict(set)
    dashes: dict[str, set[dt.date]] = defaultdict(set)
    mismatches: list[str] = []
    unusual: list[str] = []
    checked = 0
    for key in keys:
        for zone in sheets[key]:
            listed.add(zone.zone)
            values = [price for price in zone.prices.values() if price is not None]
            if values and zone.average is not None:
                checked += 1
                mean = round(sum(values) / len(values), 2)
                if abs(mean - zone.average) > 0.011:
                    mismatches.append(f"{_label(key)} {zone.zone}: ours {mean:g}, sheet {zone.average:g}")
            for date, price in zone.prices.items():
                if price is None:
                    dashes[zone.zone].add(date)
                    continue
                kinds[zone.zone].add(zone.kind)
                priced[zone.zone].add(date)
                first.setdefault(zone.zone, date)
                last[zone.zone] = date
                per_year[zone.zone][date.year] += 1
                if not 50 <= price <= 2000:
                    unusual.append(f"{date} {zone.zone}: {price:g}")

    zones = sorted(first, key=lambda name: (first[name], name))
    never_priced = sorted(listed - set(first))
    years = range(keys[0][0], keys[-1][0] + 1)
    lines = [
        "NECC daily egg prices: backfill report",
        f"Generated {dt.datetime.now(IST):%Y-%m-%d %H:%M} IST from {len(keys)} daily sheets, "
        f"{_label(keys[0])} to {_label(keys[-1])}",
        f"{row_count} price rows in {CSV_PATH.relative_to(ROOT)} (prices are ₹ per 100 eggs)",
        f"Sheets without a price table: {', '.join(_label(k) for k in keys if not sheets[k]) or 'none'}",
        f"Average check: {checked} zone-months compared with the sheet's Average column, "
        f"{len(mismatches)} differ",
        *(f"  {line}" for line in mismatches[:20]),
        "",
        "Zones by first priced date (gaps = '-' days between the first and last price):",
        f"  {'zone':<20} {'type':<20} {'first':<10} {'last':<10} {'days':>5} {'gaps':>5}  note",
    ]
    for name in zones:
        # A zone can also sit in the other section as an all-'-' row; those days are not gaps.
        gaps = sum(first[name] < date < last[name] for date in dashes[name] - priced[name])
        note = "" if name in latest else "not in latest sheet"
        lines.append(
            f"  {name:<20} {'/'.join(sorted(kinds[name])):<20} {first[name]} {last[name]} "
            f"{sum(per_year[name].values()):>5} {gaps:>5}  {note}"
        )
    if never_priced:
        lines.append(f"  Listed but never priced: {', '.join(never_priced)}")
    lines += ["", "Priced days per year:", f"  {'zone':<20}" + "".join(f"{year:>5}" for year in years)]
    for name in zones:
        lines.append(f"  {name:<20}" + "".join(f"{per_year[name][year] or '':>5}" for year in years))
    lines += ["", f"Prices outside 50-2000: {len(unusual)}", *(f"  {line}" for line in unusual[:20])]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def backfill(args: argparse.Namespace) -> int:
    today = dt.datetime.now(IST).date()
    current = (today.year, today.month)
    end = args.end or current
    context = ssl_context(args.ca_file)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    for year, month in _months(args.start, end):
        path = _raw_path(year, month)
        # The current month keeps changing, so it is always fetched again.
        if path.exists() and not args.refresh and (year, month) != current:
            continue
        if downloaded:
            time.sleep(REQUEST_GAP_SECONDS)
        html = fetch_sheet(year, month, context)
        read_page(html, year, month)
        path.write_text(html, encoding="utf-8")
        downloaded += 1
        print(f"{_label((year, month))} downloaded", flush=True)

    sheets = {
        (year, month): parse_sheet(_raw_path(year, month).read_text(encoding="utf-8"), year, month, today)
        for year, month in _months(args.start, end)
    }
    rows: Rows = {}
    for zones in sheets.values():
        rows.update(sheet_rows(zones))
    write_csv(rows)
    write_report(sheets, len(rows))
    write_app_json(rows)
    print(
        f"{downloaded} sheets downloaded, {len(sheets)} parsed, {len(rows)} rows -> "
        f"{CSV_PATH.relative_to(ROOT)}; report -> {REPORT_PATH.relative_to(ROOT)}; "
        f"app prices -> {APP_JSON_PATH.relative_to(ROOT)}"
    )
    return 0


def update(args: argparse.Namespace) -> int:
    if not CSV_PATH.exists():
        raise ValueError(f"{CSV_PATH.relative_to(ROOT)} not found; run backfill first")
    today = dt.datetime.now(IST).date()
    stored = read_csv()
    # Re-reading the last week also picks up zones that NECC filled in late, across a month change.
    since = max(date for date, _ in stored) - dt.timedelta(days=7)
    context = ssl_context(args.ca_file)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    rows = dict(stored)
    for index, (year, month) in enumerate(_months((since.year, since.month), (today.year, today.month))):
        if index:
            time.sleep(REQUEST_GAP_SECONDS)
        html = fetch_sheet(year, month, context)
        fetched = sheet_rows(parse_sheet(html, year, month, today))
        _raw_path(year, month).write_text(html, encoding="utf-8")
        added = sum(key not in stored for key in fetched)
        changed = sum(key in stored and stored[key] != value for key, value in fetched.items())
        # Stored prices the page no longer shows are kept, so a partial page can't erase history.
        hidden = sum(
            (date.year, date.month) == (year, month) and (date, zone) not in fetched for date, zone in stored
        )
        rows.update(fetched)
        print(f"{_label((year, month))}: {added} new, {changed} changed, {hidden} no longer shown (kept)")
        if CLARIFICATION not in " ".join(html.split()):
            print("warning: NECC's clarification text changed; update CLARIFICATION", file=sys.stderr)

    csv_changed = rows != stored
    if csv_changed:
        write_csv(rows)
    json_changed = write_app_json(rows)
    print(f"{CSV_PATH.relative_to(ROOT)}: {'updated' if csv_changed else 'no changes'}, {len(rows)} rows")
    print(f"{APP_JSON_PATH.relative_to(ROOT)}: {'updated' if json_changed else 'no changes'}")
    for _, name, necc_name in APP_ZONES:
        last = max(date for date, zone in rows if zone == necc_name)
        print(f"  {name:<11} {rows[(last, necc_name)][1]:g} on {last}")
    return 0


def _price(text: str) -> float | None:
    text = text.replace(",", "")
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"not a price: {text!r}") from None


def _json_number(price: float | None) -> float | int | None:
    if price is None:
        return None
    return int(price) if price.is_integer() else round(price, 2)


def _months(start: tuple[int, int], end: tuple[int, int]):
    year, month = start
    while (year, month) <= end:
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _raw_path(year: int, month: int) -> Path:
    return RAW_DIR / f"necc_daily_{year}_{month:02d}.html"


def _label(key: tuple[int, int]) -> str:
    return f"{key[0]}-{key[1]:02d}"


def _month_arg(text: str) -> tuple[int, int]:
    try:
        year, month = (int(part) for part in text.split("-"))
        dt.date(year, month, 1)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM, got {text!r}") from None
    return year, month


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NECC daily egg price data")
    network = argparse.ArgumentParser(add_help=False)
    network.add_argument("--ca-file", help="extra root certificate (PEM) to trust, e.g. a proxy's")
    commands = parser.add_subparsers(dest="command", required=True)
    backfill_parser = commands.add_parser(
        "backfill", parents=[network], help="download every daily sheet once and rebuild the CSV"
    )
    backfill_parser.add_argument("--start", type=_month_arg, default=(2009, 1), help="first month, YYYY-MM")
    backfill_parser.add_argument("--end", type=_month_arg, help="last month, YYYY-MM (default: this month)")
    backfill_parser.add_argument("--refresh", action="store_true", help="re-download sheets already in Data/raw")
    backfill_parser.set_defaults(run=backfill)
    update_parser = commands.add_parser(
        "update", parents=[network], help="re-read recent months; update the CSV and the app's price file"
    )
    update_parser.set_defaults(run=update)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
