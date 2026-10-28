import Foundation

/// The bundled month pattern written by `Analysis/exploration.ipynb`.
struct MonthPatternFile: Decodable {
    /// First and last months of NECC prices used, as "yyyy-MM".
    let firstMonth: String
    let lastMonth: String
    let zones: [ZoneMonthPattern]
}

struct ZoneMonthPattern: Decodable, Identifiable {
    let id: String
    let name: String
    let months: [MonthStat]
    let periods: [DemandPeriod]
}

/// How a calendar month's NECC price usually compares with the 12 months around it, in percent.
struct MonthStat: Decodable, Identifiable {
    let month: Int
    /// Median across years.
    let percent: Double
    /// Middle half of years: the 25th to 75th percentile.
    let low: Double
    let high: Double
    let yearsAbove: Int
    let years: Int

    var id: Int { month }
}

/// A festival or season, its coming dates and what it did to NECC prices in past years.
struct DemandPeriod: Decodable, Identifiable {
    enum Effect: String, Decodable, CaseIterable {
        case lower
        case higher
        case unclear
    }

    /// Inclusive "yyyy-MM-dd" dates.
    struct Dates: Decodable {
        let start: String
        let end: String
    }

    let id: String
    let name: String
    let effect: Effect
    /// Follows the moon, so the dates move from year to year.
    let datesShift: Bool
    let note: String
    /// The dates in progress or next when the file was made, then the ones after.
    let dates: [Dates]
}

/// A period with the dates that matter on a given day.
struct ComingPeriod: Identifiable {
    let period: DemandPeriod
    let dates: ClosedRange<Date>

    var id: String { period.id }

    /// "27 Oct – 24 Nov 2026"; fixed-date periods leave out the year, as they repeat every year.
    var datesText: String {
        let days = dates.lowerBound..<dates.upperBound
        return period.datesShift
            ? days.formatted(.interval.day().month(.abbreviated).year())
            : days.formatted(.interval.day().month(.abbreviated))
    }
}

extension ZoneMonthPattern {
    var highestMonths: [Int] {
        months.sorted { $0.percent > $1.percent }.prefix(3).map(\.month)
    }

    var lowestMonths: [Int] {
        months.sorted { $0.percent < $1.percent }.prefix(3).map(\.month)
    }

    /// Each period's dates in progress or next on `day`, soonest first; the last known dates once all have passed.
    func comingPeriods(on day: Date) -> [ComingPeriod] {
        periods.compactMap { period in
            let all = period.dates.compactMap { dates -> ClosedRange<Date>? in
                guard let start = PriceCalendar.date(fromISODay: dates.start),
                      let end = PriceCalendar.date(fromISODay: dates.end), start <= end else { return nil }
                return start...end
            }
            return (all.first { $0.upperBound >= day } ?? all.last).map { ComingPeriod(period: period, dates: $0) }
        }
        .sorted { $0.dates.lowerBound < $1.dates.lowerBound }
    }
}

/// A 365-day year counted in days from 1 January, so month bars and festival dates share one x-axis.
enum YearAxis {
    static let length = 365.0
    private static let monthLengths = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    static func start(ofMonth month: Int) -> Double {
        Double(monthLengths.prefix(month - 1).reduce(0, +))
    }

    static func end(ofMonth month: Int) -> Double {
        start(ofMonth: month) + Double(monthLengths[month - 1])
    }

    static func middle(ofMonth month: Int) -> Double {
        (start(ofMonth: month) + end(ofMonth: month)) / 2
    }

    static func month(atDay day: Double) -> Int {
        (1...12).last { start(ofMonth: $0) <= day } ?? 1
    }

    /// 29 February shares 28 February's place.
    static func day(of date: Date) -> Double {
        let parts = PriceCalendar.calendar.dateComponents([.month, .day], from: date)
        let month = parts.month ?? 1
        return start(ofMonth: month) + Double(min(parts.day ?? 1, monthLengths[month - 1]) - 1)
    }

    /// Days on the axis, end exclusive; dates that run past 31 December are split in two.
    static func dayRanges(_ dates: ClosedRange<Date>) -> [Range<Double>] {
        let startDay = day(of: dates.lowerBound)
        let endDay = day(of: dates.upperBound) + 1
        if startDay < endDay {
            return [startDay..<endDay]
        }
        return [startDay..<length, 0..<endDay]
    }

    static func monthName(_ month: Int, abbreviated: Bool = true) -> String {
        let calendar = Calendar.current
        let names = abbreviated ? calendar.shortStandaloneMonthSymbols : calendar.standaloneMonthSymbols
        return names[month - 1]
    }
}
