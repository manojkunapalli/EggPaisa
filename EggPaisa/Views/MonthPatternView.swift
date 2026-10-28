import SwiftUI

/// The months when a zone's NECC price is usually high or low, with festival and season periods.
struct MonthPatternView: View {
    @Environment(PriceStore.self) private var store
    @State private var zoneID: String?

    init(zoneID: String? = nil) {
        _zoneID = State(initialValue: zoneID)
    }

    var body: some View {
        Group {
            if let file = store.monthPatterns, let pattern = pattern(in: file) {
                list(file: file, pattern: pattern)
            } else {
                ContentUnavailableView(
                    "High-price months unavailable",
                    systemImage: "exclamationmark.triangle",
                    description: Text(store.monthPatternError ?? "")
                )
            }
        }
        .navigationTitle("High-price months")
    }

    private func pattern(in file: MonthPatternFile) -> ZoneMonthPattern? {
        file.zones.first { $0.id == zoneID } ?? file.zones.first
    }

    private func list(file: MonthPatternFile, pattern: ZoneMonthPattern) -> some View {
        let today = PriceCalendar.today()
        let periods = pattern.comingPeriods(on: today)
        return List {
            Section {
                Picker("Zone", selection: Binding(get: { pattern.id }, set: { zoneID = $0 })) {
                    ForEach(file.zones) { zone in
                        Text(zone.name)
                            .tag(zone.id)
                    }
                }
                LabeledContent("Usually highest", value: monthList(pattern.highestMonths))
                LabeledContent("Usually lowest", value: monthList(pattern.lowestMonths))
            }
            Section {
                VStack(spacing: 20) {
                    MonthPatternChart(
                        months: pattern.months,
                        yearlyAverage: store.zones.first { $0.id == pattern.id }?.lastYearAverage
                    )
                    DemandPeriodChart(periods: periods)
                }
                .padding(.vertical, 8)
            } header: {
                Text("Price vs yearly average, %")
            } footer: {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Bars: how far each month's price usually is above (green) or below (red) the yearly average.")
                    Text(
                        """
                        Prices rise over the years, so each month is compared with the average of the 12 months \
                        around it, not with one average for \(monthRange(file)). A bar is the middle value across \
                        those years; its thin line covers the middle half of them.
                        """
                    )
                    Text("Rupee amounts apply a bar to the last 12 months' average.")
                    Text("Bottom: festivals and seasons at their next dates; faded ones move each year.")
                }
            }
            Section("Festivals and seasons, soonest first") {
                ForEach(periods) { coming in
                    DemandPeriodRow(coming: coming, isNow: coming.dates.contains(today))
                }
            }
        }
    }

    private func monthList(_ months: [Int]) -> String {
        months.map { YearAxis.monthName($0) }.formatted(.list(type: .and, width: .narrow))
    }

    private func monthRange(_ file: MonthPatternFile) -> String {
        let format = Date.FormatStyle.dateTime.month(.abbreviated).year()
        guard let first = PriceCalendar.date(fromISODay: file.firstMonth + "-01"),
              let last = PriceCalendar.date(fromISODay: file.lastMonth + "-01") else { return "" }
        return "\(first.formatted(format)) – \(last.formatted(format))"
    }
}

private struct DemandPeriodRow: View {
    let coming: ComingPeriod
    let isNow: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Image(systemName: "circle.fill")
                    .font(.caption2)
                    .foregroundStyle(period.effect.color)
                    .accessibilityHidden(true)
                Text(period.name)
                    .font(.headline)
                if isNow {
                    Text("Now")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .background(period.effect.color.opacity(0.2), in: .capsule)
                }
                Spacer()
                Text(period.effect.label)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(datesText)
                .font(.subheadline)
            Text(period.note)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }

    private var period: DemandPeriod { coming.period }

    private var datesText: String {
        period.datesShift ? String(localized: "\(coming.datesText) · dates shift each year") : coming.datesText
    }
}
