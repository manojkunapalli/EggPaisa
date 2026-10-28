import Foundation
import Testing
@testable import EggPaisa

struct PriceMergeTests {
    private func file(_ prices: [Double?], start: String = "2026-10-25") throws -> PriceFile {
        PriceFile(
            sourceURL: try #require(URL(string: "https://www.e2necc.com/home/eggprice")),
            lastPriceDate: "2026-10-26",
            clarification: "",
            zones: [ZoneSeries(id: "chittoor", name: "Chittoor", neccName: "Chittoor", start: start, prices: prices)]
        )
    }

    private func october(_ prices: [Int: Double], zone: String = "Chittoor") -> NECCSheet {
        NECCSheet(year: 2026, month: 10, prices: [zone: prices])
    }

    private func day(_ day: Int, month: Int = 10) throws -> Date {
        try #require(PriceCalendar.date(year: 2026, month: month, day: day))
    }

    @Test func addsNewDaysAndTakesNECCsValue() throws {
        let merged = try file([600, 610]).merging([october([26: 615, 27: 620])], through: day(27))
        #expect(merged.zones[0].prices == [600, 615, 620])
        #expect(merged.lastPriceDate == "2026-10-27")
    }

    @Test func dashNeverErases() throws {
        let merged = try file([600, 610]).merging([october([25: 600])], through: day(27))
        #expect(merged.zones[0].prices == [600, 610])
        #expect(merged.lastPriceDate == "2026-10-26")
    }

    @Test func ignoresDaysAfterTodayAndBeforeTheStart() throws {
        let merged = try file([600, 610]).merging([october([20: 500, 27: 620, 28: 630])], through: day(27))
        #expect(merged.zones[0].prices == [600, 610, 620])
    }

    @Test func ignoresOtherZones() throws {
        let original = try file([600, 610])
        let today = try day(27)
        let merged = original.merging([october([27: 999], zone: "Namakkal")], through: today)
        #expect(merged == original)
    }

    @Test func mergesAcrossMonths() throws {
        let november = NECCSheet(year: 2026, month: 11, prices: ["Chittoor": [1: 650]])
        let merged = try file([600, 610]).merging([october([31: 640]), november], through: day(1, month: 11))
        #expect(merged.zones[0].prices == [600, 610, nil, nil, nil, nil, 640, 650])
        #expect(merged.lastPriceDate == "2026-11-01")
    }

    @Test func missingDayTakesThePreviousPrice() throws {
        let series = try file([600, nil, 620]).zones[0]
        let zone = try #require(Zone(series: series))
        let lastDay = try day(27)
        #expect(zone.days.map(\.price) == [600, 600, 620])
        #expect(zone.days.map(\.isCarriedForward) == [false, true, false])
        #expect(zone.latest?.date == lastDay)
        #expect(zone.change == 20)
    }
}
