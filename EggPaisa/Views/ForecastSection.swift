import SwiftUI

/// The zone's next 14 days from the daily forecast: each day's most likely price range and its chance.
struct ForecastSection: View {
    let zoneID: String
    /// The zone's newest NECC price; only later days are shown.
    let latestPrice: Date?
    @Environment(ForecastStore.self) private var forecasts

    var body: some View {
        let today = PriceCalendar.today()
        let file = forecasts.forecast.flatMap { $0.isRecent(on: today) ? $0 : nil }
        let days = file?.days(for: zoneID, after: latestPrice, from: today) ?? []
        Section {
            if days.isEmpty {
                Text(missingText(today: today))
                    .foregroundStyle(.secondary)
            } else {
                ForEach(days) { day in
                    ForecastRow(day: day)
                }
            }
        } header: {
            Text("Next 14 days")
        } footer: {
            if let file, !days.isEmpty {
                Text(note(for: file))
            }
        }
    }

    private func note(for file: ForecastFile) -> String {
        let ranges = String(localized: """
            The most likely ₹10 range for the first \(ForecastFile.narrowDays) days ahead, then ₹20; \
            the % is how often such ranges came true over the past year.
            """)
        let origin = file.originDate?.formatted(.dateTime.day().month(.abbreviated)) ?? file.origin
        let made: String
        if let generated = file.generatedDate {
            let time = generated.formatted(.dateTime.day().month(.abbreviated).hour().minute())
            made = String(localized: "Forecast made \(time) from NECC prices of \(origin).")
        } else {
            made = String(localized: "Forecast from NECC prices of \(origin).")
        }
        return "\(ranges) \(made) " + String(localized: "Forecasts can be wrong.")
    }

    private func missingText(today: Date) -> String {
        guard let forecast = forecasts.forecast else {
            return String(localized: "The forecast downloads when you're online.")
        }
        if !forecast.isRecent(on: today), let origin = forecast.originDate {
            let day = origin.formatted(.dateTime.day().month(.abbreviated))
            return String(localized: """
                The saved forecast, from NECC prices of \(day), is too old to show. \
                A new one downloads when you're online.
                """)
        }
        return String(localized: "No forecast for this zone right now.")
    }
}

private struct ForecastRow: View {
    let day: DayForecast

    var body: some View {
        HStack {
            Text(day.date, format: .dateTime.weekday(.abbreviated).day().month(.abbreviated))
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text("\(PriceFormat.rupees(day.range.low))–\(PriceFormat.number(day.range.high))")
                    .font(.body.weight(.semibold))
                    .monospacedDigit()
                Text("\(PriceFormat.chance(day.range.chance)) chance")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
