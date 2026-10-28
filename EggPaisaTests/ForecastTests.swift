import Foundation
import Testing
@testable import EggPaisa

struct ForecastTests {
    /// Shaped like Pipeline/forecast.py's output, extra keys included; day h's ₹10 range starts at 600 + h.
    private func sample(origin: String = "2026-10-27") throws -> ForecastFile {
        let start = try #require(PriceCalendar.date(fromISODay: origin))
        let days = (1...14).map { ahead in
            let date = PriceCalendar.isoDay(PriceCalendar.day(ahead, after: start))
            return """
                {"date": "\(date)", "forecast": 633.0,
                 "range10": {"low": \(600 + ahead), "high": \(610 + ahead), "chance": 0.8},
                 "range20": {"low": \(590 + ahead), "high": \(610 + ahead), "chance": 0.9}}
                """
        }
        let json = """
            {"generated": "2026-10-27T20:17:15+05:30", "origin": "\(origin)", "unit": "₹ per 100 eggs",
             "method": "Boosting", "zones": [{"id": "chittoor", "name": "Chittoor", "price": 633,
             "priceDate": "\(origin)", "days": [\(days.joined(separator: ","))]}]}
            """
        return try JSONDecoder().decode(ForecastFile.self, from: Data(json.utf8))
    }

    private func day(_ day: Int, month: Int = 10) throws -> Date {
        try #require(PriceCalendar.date(year: 2026, month: month, day: day))
    }

    @Test func readsTheForecastFile() throws {
        let file = try sample()
        let origin = try day(27)
        #expect(file.originDate == origin)
        #expect(file.generatedDate == Date(timeIntervalSince1970: 1_793_112_435))
        #expect(file.zones.first?.days.count == 14)
    }

    @Test func hidesForecastsOlderThanThreeDays() throws {
        let file = try sample()
        let (origin, third, fourth) = try (day(27), day(30), day(31))
        #expect(file.isRecent(on: origin))
        #expect(file.isRecent(on: third))
        #expect(!file.isRecent(on: fourth))
    }

    @Test func firstWeekUsesTenRupeeRangesThenTwenty() throws {
        let days = try sample().days(for: "chittoor", after: day(27), from: day(28))
        let tomorrow = try day(28)
        #expect(days.count == 14)
        #expect(days.first?.date == tomorrow)
        #expect(days.prefix(7).map(\.range.low) == Array(601...607).map(Double.init))
        #expect(days.prefix(7).allSatisfy { $0.range.high - $0.range.low == 10 })
        #expect(days.dropFirst(7).map(\.range.low) == Array(598...604).map(Double.init))
        #expect(days.dropFirst(7).allSatisfy { $0.range.high - $0.range.low == 20 })
    }

    @Test func leavesOutDaysAlreadyPricedOrPast() throws {
        let file = try sample()
        let (newPrice, laterToday) = try (day(28), day(30))
        let afterNewPrice = file.days(for: "chittoor", after: newPrice, from: newPrice)
        #expect(afterNewPrice.first?.date == PriceCalendar.day(1, after: newPrice))
        #expect(afterNewPrice.count == 13)
        let twoDaysLater = try file.days(for: "chittoor", after: day(27), from: laterToday)
        #expect(twoDaysLater.first?.date == laterToday)
        try #require(twoDaysLater.count == 12)
        // The day number still sets the range: the 8th day ahead is a ₹20 range wherever the list starts.
        #expect(twoDaysLater[5].range.high - twoDaysLater[5].range.low == 20)
    }

    @Test func unknownZoneHasNoDays() throws {
        let days = try sample().days(for: "barwala", after: day(27), from: day(28))
        #expect(days.isEmpty)
    }
}
