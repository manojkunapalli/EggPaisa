import Foundation

/// The bundled price file written by `Scripts/necc.py`; the app saves its updated copy in the same shape.
struct PriceFile: Codable, Equatable {
    let sourceURL: URL
    let lastPriceDate: String
    let clarification: String
    let zones: [ZoneSeries]
}

struct ZoneSeries: Codable, Equatable {
    let id: String
    let name: String
    let neccName: String
    let start: String
    /// One price per day from `start`; `nil` where NECC showed "-".
    let prices: [Double?]
}

extension PriceFile {
    /// Adds the sheets' prices up to `today`, as `necc.py update` does: NECC's value wins, and "-" never erases.
    func merging(_ sheets: [NECCSheet], through today: Date) -> PriceFile {
        let merged = zones.map { $0.merging(sheets, through: today) }
        return PriceFile(
            sourceURL: sourceURL,
            lastPriceDate: merged.compactMap(\.lastDate).max().map(PriceCalendar.isoDay) ?? lastPriceDate,
            clarification: clarification,
            zones: merged
        )
    }
}

extension ZoneSeries {
    var lastDate: Date? {
        guard let first = PriceCalendar.date(fromISODay: start),
              let last = prices.lastIndex(where: { $0 != nil }) else { return nil }
        return PriceCalendar.day(last, after: first)
    }

    func merging(_ sheets: [NECCSheet], through today: Date) -> ZoneSeries {
        guard let first = PriceCalendar.date(fromISODay: start) else { return self }
        var prices = prices
        for sheet in sheets {
            for (day, price) in sheet.prices[neccName] ?? [:] {
                guard let date = PriceCalendar.date(year: sheet.year, month: sheet.month, day: day),
                      date <= today else { continue }
                let offset = PriceCalendar.days(from: first, to: date)
                guard offset >= 0 else { continue }
                if offset >= prices.count {
                    prices.append(contentsOf: repeatElement(nil, count: offset - prices.count + 1))
                }
                prices[offset] = price
            }
        }
        return ZoneSeries(id: id, name: name, neccName: neccName, start: start, prices: prices)
    }
}

struct DailyPrice: Identifiable {
    let date: Date
    let price: Double
    /// NECC showed no price this day, so the previous day's price is used.
    let isCarriedForward: Bool

    var id: Date { date }
}

struct Zone: Identifiable {
    let id: String
    let name: String
    let neccName: String
    /// Every day from the first price to the latest; days without a NECC price repeat the previous day's.
    let days: [DailyPrice]

    var latest: DailyPrice? { days.last }

    var change: Double? {
        guard days.count > 1 else { return nil }
        return days[days.count - 1].price - days[days.count - 2].price
    }
}

extension Zone {
    init?(series: ZoneSeries) {
        guard let start = PriceCalendar.date(fromISODay: series.start) else { return nil }
        var days: [DailyPrice] = []
        days.reserveCapacity(series.prices.count)
        for (offset, price) in series.prices.enumerated() {
            let date = PriceCalendar.day(offset, after: start)
            if let price {
                days.append(DailyPrice(date: date, price: price, isCarriedForward: false))
            } else if let previous = days.last {
                days.append(DailyPrice(date: date, price: previous.price, isCarriedForward: true))
            }
        }
        self.init(id: series.id, name: series.name, neccName: series.neccName, days: days)
    }
}

/// NECC days are stored at 12:00 UTC so each one shows as the same calendar date in India.
enum PriceCalendar {
    static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = .gmt
        return calendar
    }()

    static func date(fromISODay text: String) -> Date? {
        let parts = text.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else { return nil }
        return date(year: parts[0], month: parts[1], day: parts[2])
    }

    /// `nil` for a day the month doesn't have, such as 31 September.
    static func date(year: Int, month: Int, day: Int) -> Date? {
        guard let date = calendar.date(from: DateComponents(year: year, month: month, day: day, hour: 12)),
              calendar.component(.day, from: date) == day else { return nil }
        return date
    }

    static func isoDay(_ date: Date) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    static func day(_ offset: Int, after start: Date) -> Date {
        start.addingTimeInterval(TimeInterval(offset) * 86_400)
    }

    static func days(from start: Date, to end: Date) -> Int {
        Int((end.timeIntervalSince(start) / 86_400).rounded())
    }

    /// Today's date in India, where NECC sets its prices.
    static func today(now: Date = .now) -> Date {
        var india = Calendar(identifier: .gregorian)
        india.timeZone = TimeZone(identifier: "Asia/Kolkata") ?? .gmt
        let parts = india.dateComponents([.year, .month, .day], from: now)
        let day = DateComponents(year: parts.year, month: parts.month, day: parts.day, hour: 12)
        return calendar.date(from: day) ?? now
    }
}
