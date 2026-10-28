import Foundation
import Testing
@testable import EggPaisa

/// NECC's daily sheet for October 2026, saved on the 27th.
private func octoberPage() throws -> String {
    let url = try #require(Bundle(for: BundleMarker.self).url(forResource: "necc_daily_2026_10", withExtension: "html"))
    return try String(contentsOf: url, encoding: .utf8)
}

private final class BundleMarker {}

private let chittoorDayOne = "<td align='left'>Chittoor</td><td>593</td>"

struct NECCSheetTests {
    @Test func readsEveryZoneAndPrice() throws {
        let sheet = try NECCSheet(html: octoberPage(), year: 2026, month: 10)
        #expect(sheet.prices.count == 34)
        #expect(sheet.prices["Chittoor"]?[1] == 593)
        #expect(sheet.prices["Chittoor"]?[27] == 633)
        #expect(sheet.prices["Hyderabad"]?[24] == 570)
        #expect(sheet.prices["Kolkata (WB)"]?[27] == 645)
    }

    @Test func leavesOutDaysWithoutPrice() throws {
        let sheet = try NECCSheet(html: octoberPage(), year: 2026, month: 10)
        #expect(sheet.prices["Chittoor"]?[28] == nil)
        let html = try octoberPage().replacingOccurrences(
            of: chittoorDayOne,
            with: "<td align='left'>Chittoor</td><td>-</td>"
        )
        let dashed = try NECCSheet(html: html, year: 2026, month: 10)
        #expect(dashed.prices["Chittoor"]?[1] == nil)
        #expect(dashed.prices["Chittoor"]?[2] == 593)
    }

    @Test func refusesAnotherMonth() throws {
        let html = try octoberPage()
        #expect(throws: NECCSheet.ReadError.wrongMonth) {
            try NECCSheet(html: html, year: 2026, month: 9)
        }
        #expect(throws: NECCSheet.ReadError.wrongMonth) {
            try NECCSheet(html: html, year: 2025, month: 10)
        }
    }

    @Test func refusesAnUnreadablePrice() throws {
        let html = try octoberPage().replacingOccurrences(
            of: chittoorDayOne,
            with: "<td align='left'>Chittoor</td><td>59x</td>"
        )
        #expect(throws: NECCSheet.ReadError.unexpectedTable) {
            try NECCSheet(html: html, year: 2026, month: 10)
        }
    }

    @Test func monthWithoutTableHasNoPrices() throws {
        let html = try octoberPage().replacingOccurrences(of: "Name Of Zone", with: "Nothing here")
        let sheet = try NECCSheet(html: html, year: 2026, month: 10)
        #expect(sheet.prices.isEmpty)
    }
}
