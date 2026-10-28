import SwiftUI

struct ZoneDetailView: View {
    let zoneID: String
    @Environment(PriceStore.self) private var store
    // Farmers mostly follow the last week, so the chart opens on it.
    @State private var range = HistoryRange.week

    var body: some View {
        // Looked up by ID, so new prices from NECC show up while this screen is open.
        if let zone = store.zones.first(where: { $0.id == zoneID }) {
            list(zone)
                .navigationTitle(zone.name)
        } else {
            ContentUnavailableView("Zone not found", systemImage: "exclamationmark.triangle")
        }
    }

    private func list(_ zone: Zone) -> some View {
        List {
            Section {
                LatestPriceHeader(zone: zone)
            }
            ForecastSection(zoneID: zone.id, latestPrice: zone.latest?.date)
            Section {
                Picker("Range", selection: $range) {
                    ForEach(HistoryRange.allCases) { option in
                        Text(option.rawValue)
                            .tag(option)
                    }
                }
                .pickerStyle(.segmented)
                PriceHistoryChart(
                    points: zone.points(for: range),
                    priceRange: zone.priceRange(for: range),
                    range: range
                )
            } header: {
                Text("History")
            } footer: {
                Text(historyNote)
            }
            Section {
                NavigationLink {
                    MonthPatternView(zoneID: zone.id)
                } label: {
                    Label("High-price months", systemImage: "chart.bar.xaxis")
                }
            }
            ClarificationSection(text: store.clarification)
        }
    }

    private var historyNote: LocalizedStringKey {
        switch range {
        case .week: "Daily NECC prices for the last 7 days."
        case .month, .sixMonths, .year: "Daily NECC prices. Touch the chart to read a price."
        case .fiveYears: "Weekly averages. Touch the chart to read a value."
        case .all: "Monthly averages. Touch the chart to read a value."
        }
    }
}

private struct LatestPriceHeader: View {
    let zone: Zone

    var body: some View {
        if let latest = zone.latest {
            VStack(alignment: .leading, spacing: 6) {
                Text(PriceFormat.rupees(latest.price))
                    .font(.largeTitle.weight(.bold))
                    .monospacedDigit()
                ChangeLabel(change: zone.change)
                    .font(.subheadline)
                Text("\(zone.neccName) · \(latest.date, format: .dateTime.day().month(.wide).year()) · ₹ per 100 eggs")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
        }
    }
}
