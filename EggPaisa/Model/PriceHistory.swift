import Foundation

enum HistoryRange: String, CaseIterable, Identifiable {
    case week = "1W"
    case month = "1M"
    case sixMonths = "6M"
    case year = "1Y"
    case fiveYears = "5Y"
    case all = "All"

    var id: Self { self }

    /// Most recent days shown; `nil` shows the full history.
    var dayCount: Int? {
        switch self {
        case .week: 7
        case .month: 31
        case .sixMonths: 183
        case .year: 366
        case .fiveYears: 1_827
        case .all: nil
        }
    }

    var isDaily: Bool {
        switch self {
        case .week, .month, .sixMonths, .year: true
        case .fiveYears, .all: false
        }
    }
}

struct ChartPoint: Identifiable {
    let date: Date
    let price: Double
    let isCarriedForward: Bool

    var id: Date { date }
}

extension Zone {
    /// Lowest and highest daily price over the days the range shows.
    func priceRange(for range: HistoryRange) -> ClosedRange<Double>? {
        let prices = (range.dayCount.map { days.suffix($0) } ?? days[...]).map(\.price)
        guard let low = prices.min(), let high = prices.max() else { return nil }
        return low...high
    }

    /// Average daily price over the last 365 days: today's level for the High-price months percentages.
    var lastYearAverage: Double? {
        let recent = days.suffix(365)
        guard !recent.isEmpty else { return nil }
        return recent.reduce(0) { $0 + $1.price } / Double(recent.count)
    }

    /// Daily prices up to a year; weekly (5Y) or monthly (All) averages keep long charts light.
    func points(for range: HistoryRange) -> [ChartPoint] {
        let recent = range.dayCount.map { Array(days.suffix($0)) } ?? days
        switch range {
        case .week, .month, .sixMonths, .year:
            return recent.map { ChartPoint(date: $0.date, price: $0.price, isCarriedForward: $0.isCarriedForward) }
        case .fiveYears:
            // Weeks are counted back from the latest day, so the last point is the current week.
            return Self.averages(of: recent) { index, _ in (recent.count - 1 - index) / 7 }
        case .all:
            return Self.averages(of: recent) { _, day in
                let parts = PriceCalendar.calendar.dateComponents([.year, .month], from: day.date)
                return (parts.year ?? 0) * 12 + (parts.month ?? 0)
            }
        }
    }

    private static func averages(of days: [DailyPrice], bucket: (Int, DailyPrice) -> Int) -> [ChartPoint] {
        var points: [ChartPoint] = []
        var group: [DailyPrice] = []
        var groupBucket: Int?
        for (index, day) in days.enumerated() {
            let dayBucket = bucket(index, day)
            if dayBucket != groupBucket, !group.isEmpty {
                points.append(average(of: group))
                group.removeAll(keepingCapacity: true)
            }
            groupBucket = dayBucket
            group.append(day)
        }
        if !group.isEmpty {
            points.append(average(of: group))
        }
        return points
    }

    private static func average(of group: [DailyPrice]) -> ChartPoint {
        let total = group.reduce(0) { $0 + $1.price }
        return ChartPoint(
            date: group[group.count / 2].date,
            price: total / Double(group.count),
            isCarriedForward: false
        )
    }
}
