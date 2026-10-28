import Charts
import SwiftUI

/// Festival and season periods on the same year axis as `MonthPatternChart`, one row each.
struct DemandPeriodChart: View {
    let periods: [ComingPeriod]

    var body: some View {
        Chart(spans) { span in
            BarMark(
                xStart: .value("Start", span.days.lowerBound),
                xEnd: .value("End", span.days.upperBound),
                y: .value("Period", span.period.name),
                height: .fixed(10)
            )
            .foregroundStyle(by: .value("Effect", span.period.effect.label))
            .opacity(span.period.datesShift ? 0.6 : 1)
            .annotation(position: .top, alignment: .leading, spacing: 2, overflowResolution: Self.labelOverflow) {
                if span.isLabelled {
                    Text(span.period.name)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .accessibilityLabel(span.period.name)
            .accessibilityValue(span.datesText)
            .accessibilityHidden(!span.isLabelled)
        }
        .chartForegroundStyleScale(
            domain: DemandPeriod.Effect.allCases.map(\.label),
            range: DemandPeriod.Effect.allCases.map(\.color)
        )
        .chartXScale(domain: 0...YearAxis.length)
        .chartYScale(domain: rows.map(\.period.name))
        .chartXAxis { YearAxis.monthMarks() }
        .chartYAxis(.hidden)
        .chartLegend(position: .bottom, alignment: .leading)
        .frame(height: CGFloat(rows.count) * 30 + 50)
        .padding(.top, 6)
    }

    private static let labelOverflow = AnnotationOverflowResolution(x: .fit(to: .chart), y: .disabled)

    /// January to December, so the bars step down the chart through the year.
    private var rows: [ComingPeriod] {
        periods.sorted { YearAxis.day(of: $0.dates.lowerBound) < YearAxis.day(of: $1.dates.lowerBound) }
    }

    private var spans: [PeriodSpan] {
        var spans: [PeriodSpan] = []
        for coming in rows {
            let ranges = YearAxis.dayRanges(coming.dates)
            // A period that runs past 31 December is named on its longer part.
            let longest = ranges.max { $0.upperBound - $0.lowerBound < $1.upperBound - $1.lowerBound }
            for days in ranges {
                spans.append(PeriodSpan(coming: coming, days: days, isLabelled: days == longest))
            }
        }
        return spans
    }
}

private struct PeriodSpan: Identifiable {
    let coming: ComingPeriod
    let days: Range<Double>
    let isLabelled: Bool

    var period: DemandPeriod { coming.period }
    var datesText: String { coming.datesText }
    var id: String { "\(period.id)-\(days.lowerBound)" }
}

extension DemandPeriod.Effect {
    var label: String {
        switch self {
        case .lower: String(localized: "Lower prices")
        case .higher: String(localized: "Higher prices")
        case .unclear: String(localized: "No clear effect")
        }
    }

    var color: Color {
        switch self {
        case .lower: .indigo
        case .higher: .orange
        case .unclear: .gray
        }
    }
}
