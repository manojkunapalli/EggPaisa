import Foundation

/// The 14-day forecast the daily GitHub job publishes as forecast.json (`Pipeline/forecast.py`).
struct ForecastFile: Decodable {
    /// When it was made, ISO 8601 in Indian time.
    let generated: String
    /// The day of the newest NECC prices it starts from.
    let origin: String
    let zones: [ZoneForecast]
}

struct ZoneForecast: Decodable {
    let id: String
    /// One per day ahead, in order.
    let days: [ForecastDay]
}

struct ForecastDay: Decodable {
    let date: String
    let range10: ForecastRange
    let range20: ForecastRange
}

/// The most likely price range, both ends included, and how often such ranges were right over the past year.
struct ForecastRange: Decodable, Equatable {
    let low: Double
    let high: Double
    /// From 0 to 1.
    let chance: Double
}

/// One day on a zone's screen.
struct DayForecast: Identifiable {
    let date: Date
    let range: ForecastRange
    var id: Date { date }
}

extension ForecastFile {
    /// Older forecasts are hidden, as they miss what prices did since.
    static let maxAgeDays = 3
    /// Days ahead shown with the ₹10 range; later days get the ₹20 range, as ₹10 is rarely right that far out.
    static let narrowDays = 7

    var originDate: Date? { PriceCalendar.date(fromISODay: origin) }

    var generatedDate: Date? { try? Date(generated, strategy: .iso8601) }

    func isRecent(on today: Date) -> Bool {
        guard let originDate else { return false }
        return PriceCalendar.days(from: originDate, to: today) <= Self.maxAgeDays
    }

    /// The zone's days from `today` that NECC hasn't priced yet, i.e. after `latestPrice`.
    func days(for zoneID: String, after latestPrice: Date?, from today: Date) -> [DayForecast] {
        guard let zone = zones.first(where: { $0.id == zoneID }) else { return [] }
        return zone.days.enumerated().compactMap { index, day in
            guard let date = PriceCalendar.date(fromISODay: day.date), date >= today,
                  latestPrice.map({ date > $0 }) ?? true else { return nil }
            return DayForecast(date: date, range: index < Self.narrowDays ? day.range10 : day.range20)
        }
    }
}
