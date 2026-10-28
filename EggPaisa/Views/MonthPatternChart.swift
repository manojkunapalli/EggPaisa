import Charts
import SwiftUI

/// Twelve bars: how far each month's NECC price usually sits above or below the yearly average.
struct MonthPatternChart: View {
    let months: [MonthStat]
    /// The zone's average price over the last 12 months, to turn the percentages into rupees.
    let yearlyAverage: Double?
    @State private var selectedDay: Double?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            readout
            chart
        }
    }

    /// Details of the touched month above the chart, where they don't cover any bars.
    private var readout: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let selected {
                Text(title(for: selected))
                    .font(.headline)
                Text(detail(for: selected))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2, reservesSpace: true)
            } else if let yearlyAverage {
                Text("Yearly average now: \(PriceFormat.rupees(yearlyAverage.rounded()))")
                    .font(.headline)
                Text("Average NECC price over the last 12 months. Touch a bar for that month's usual price.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2, reservesSpace: true)
            } else {
                Text("Usual price by month")
                    .font(.headline)
                Text("Touch a bar to see how that month compares with the yearly average.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2, reservesSpace: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    private var chart: some View {
        Chart {
            ForEach(months) { stat in
                RectangleMark(
                    xStart: .value("Month start", YearAxis.start(ofMonth: stat.month) + Self.barGap),
                    xEnd: .value("Month end", YearAxis.end(ofMonth: stat.month) - Self.barGap),
                    yStart: .value("Yearly average", 0.0),
                    yEnd: .value("Usual difference", stat.percent)
                )
                .foregroundStyle(stat.percent >= 0 ? Color.green : Color.red)
                .opacity(selected == nil || selected?.month == stat.month ? 1 : 0.4)
                .accessibilityLabel(YearAxis.monthName(stat.month, abbreviated: false))
                .accessibilityValue(PriceFormat.percent(stat.percent))
                RuleMark(
                    x: .value("Month", YearAxis.middle(ofMonth: stat.month)),
                    yStart: .value("Low", stat.low),
                    yEnd: .value("High", stat.high)
                )
                .foregroundStyle(Color.primary.opacity(0.5))
                .annotation(position: stat.percent >= 0 ? .top : .bottom, spacing: 2) {
                    // No % sign, so neighbouring labels don't run into each other.
                    Text(PriceFormat.signedWhole(stat.percent))
                        .font(.caption2)
                        .monospacedDigit()
                }
                .accessibilityHidden(true)
            }
            RuleMark(y: .value("Yearly average", 0.0))
                .foregroundStyle(Color.secondary)
        }
        .chartXScale(domain: 0...YearAxis.length)
        .chartYScale(domain: yDomain)
        .chartXAxis { YearAxis.monthMarks() }
        .chartYAxis(.hidden)
        .chartXSelection(value: $selectedDay)
        .frame(height: 220)
    }

    private static let barGap = 3.0

    private var selected: MonthStat? {
        guard let selectedDay else { return nil }
        let month = YearAxis.month(atDay: selectedDay)
        return months.first { $0.month == month }
    }

    private var yDomain: ClosedRange<Double> {
        let low = min(0, months.map(\.low).min() ?? 0)
        let high = max(0, months.map(\.high).max() ?? 0)
        // Room for the value labels beyond the lines.
        let padding = max((high - low) * 0.2, 4)
        return (low - padding)...(high + padding)
    }

    private func title(for stat: MonthStat) -> String {
        let month = YearAxis.monthName(stat.month, abbreviated: false)
        let percent = PriceFormat.percent(stat.percent)
        guard let yearlyAverage else {
            return String(localized: "\(month): \(percent) vs yearly average")
        }
        let price = PriceFormat.rupees((yearlyAverage * (1 + stat.percent / 100)).rounded())
        return String(localized: "\(month): \(percent), about \(price)")
    }

    private func detail(for stat: MonthStat) -> String {
        let years = stat.percent >= 0
            ? String(localized: "Above the yearly average in \(stat.yearsAbove) of \(stat.years) years.")
            : String(localized: "Below the yearly average in \(stat.years - stat.yearsAbove) of \(stat.years) years.")
        let middle = String(
            localized: "Middle half of years: \(PriceFormat.percent(stat.low)) to \(PriceFormat.percent(stat.high))."
        )
        return "\(years) \(middle)"
    }
}

extension YearAxis {
    /// Grid lines at month boundaries, with month names centred under each month.
    @AxisContentBuilder
    static func monthMarks() -> some AxisContent {
        AxisMarks(values: (1...12).map { start(ofMonth: $0) } + [length]) { _ in
            AxisGridLine()
        }
        AxisMarks(values: (1...12).map { middle(ofMonth: $0) }) { value in
            // Centred on mid-month; the default anchor starts the name there, pushing December off the edge.
            AxisValueLabel(anchor: .top) {
                Text(monthName(value.index + 1))
            }
        }
    }
}
