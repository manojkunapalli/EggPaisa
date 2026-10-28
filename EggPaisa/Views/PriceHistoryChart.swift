import Charts
import SwiftUI

struct PriceHistoryChart: View {
    let points: [ChartPoint]
    /// Lowest and highest daily price over the same days.
    let priceRange: ClosedRange<Double>?
    let range: HistoryRange
    @State private var selectedDate: Date?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // A fixed line above the chart, not a bubble on it, so the value is never cut off or hidden.
            VStack(alignment: .leading, spacing: 2) {
                Text(readoutValue)
                    .font(.title3.weight(.semibold))
                    .monospacedDigit()
                Text(readoutDetail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .accessibilityElement(children: .combine)
            chart
        }
        .padding(.vertical, 8)
    }

    private var chart: some View {
        Chart {
            ForEach(points) { point in
                LineMark(x: .value("Date", point.date), y: .value("Price", point.price))
                    .interpolationMethod(range.isDaily ? .stepEnd : .linear)
            }
            if range == .week {
                // Seven days are few enough to show every price without touching the chart.
                ForEach(Array(points.enumerated()), id: \.element.id) { index, point in
                    let fell = index > 0 && point.price < points[index - 1].price
                    PointMark(x: .value("Date", point.date), y: .value("Price", point.price))
                        .symbolSize(30)
                        // Below a price that fell, so the label clears the step down into it.
                        .annotation(position: fell ? .bottom : .top, spacing: 4) {
                            Text(PriceFormat.number(point.price))
                                .font(.caption2)
                                .monospacedDigit()
                        }
                }
            }
            if let selected {
                RuleMark(x: .value("Date", selected.date))
                    .foregroundStyle(Color.secondary.opacity(0.6))
                PointMark(x: .value("Date", selected.date), y: .value("Price", selected.price))
                    .symbolSize(60)
            }
        }
        .chartXScale(domain: xDomain)
        .chartYScale(domain: yDomain)
        .chartXAxis {
            if range == .week {
                AxisMarks(values: points.map(\.date)) { value in
                    AxisGridLine()
                    AxisValueLabel(anchor: .top) {
                        if let date = value.as(Date.self) {
                            VStack(spacing: 0) {
                                Text(date, format: .dateTime.weekday(.abbreviated))
                                Text(date, format: .dateTime.day())
                            }
                        }
                    }
                }
            } else {
                AxisMarks { value in
                    AxisGridLine()
                    AxisTick()
                    // A label this close to the right edge would be cut off.
                    if let date = value.as(Date.self), date < labelCutoff {
                        AxisValueLabel()
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 4)) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let price = value.as(Double.self) {
                        Text(PriceFormat.number(price))
                    }
                }
            }
        }
        .chartXSelection(value: $selectedDate)
        .frame(height: 220)
    }

    private var selected: ChartPoint? {
        guard let selectedDate else { return nil }
        return points.min { first, second in
            abs(first.date.timeIntervalSince(selectedDate)) < abs(second.date.timeIntervalSince(selectedDate))
        }
    }

    private var xDomain: ClosedRange<Date> {
        let first = points.first?.date ?? .now
        let last = points.last?.date ?? .now
        if range == .week {
            // Half a day either side keeps the first and last days' points and labels inside the chart.
            return first.addingTimeInterval(-43_200)...last.addingTimeInterval(43_200)
        }
        return first < last ? first...last : first...first.addingTimeInterval(86_400)
    }

    private var labelCutoff: Date {
        xDomain.upperBound.addingTimeInterval(-xDomain.lowerBound.distance(to: xDomain.upperBound) * 0.15)
    }

    /// The prices with a little room above and below, rather than stretched to round numbers.
    private var yDomain: ClosedRange<Double> {
        let prices = points.map(\.price)
        let low = prices.min() ?? 0
        let high = prices.max() ?? 0
        let padding = max((high - low) * 0.1, 5)
        // The week's price labels sit above or below the points.
        let labelRoom = range == .week ? max((high - low) * 0.3, 10) : padding
        return (low - labelRoom)...(high + labelRoom)
    }

    private var readoutValue: String {
        if let selected {
            // Weekly and monthly averages read better as whole rupees.
            return PriceFormat.rupees(range.isDaily ? selected.price : selected.price.rounded())
        }
        guard let priceRange else { return "" }
        return "\(PriceFormat.rupees(priceRange.lowerBound)) – \(PriceFormat.rupees(priceRange.upperBound))"
    }

    private var readoutDetail: String {
        guard let selected else {
            return String(localized: "Low and high, \(spanText)")
        }
        switch range {
        case .week, .month, .sixMonths, .year:
            let day = selected.date.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).year())
            return selected.isCarriedForward ? String(localized: "\(day) · no NECC price, previous day's shown") : day
        case .fiveYears:
            let day = selected.date.formatted(.dateTime.day().month(.abbreviated).year())
            return String(localized: "\(day) · weekly average")
        case .all:
            let month = selected.date.formatted(.dateTime.month(.abbreviated).year())
            return String(localized: "\(month) · monthly average")
        }
    }

    private var spanText: String {
        let span = (points.first?.date ?? .now)..<(points.last?.date ?? .now)
        return range.isDaily
            ? span.formatted(.interval.day().month(.abbreviated).year())
            : span.formatted(.interval.month(.abbreviated).year())
    }
}
