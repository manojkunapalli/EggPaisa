import SwiftUI

struct TodayView: View {
    @Environment(PriceStore.self) private var store
    @State private var showsAbout = false

    var body: some View {
        List {
            Section {
                ForEach(store.zones) { zone in
                    NavigationLink {
                        ZoneDetailView(zoneID: zone.id)
                    } label: {
                        ZoneRow(zone: zone, newestDate: store.lastPriceDate)
                    }
                }
            } header: {
                if let lastPriceDate = store.lastPriceDate {
                    Text("\(Self.dayText(lastPriceDate)) · ₹ per 100 eggs")
                }
            } footer: {
                UpdateStatus()
            }
            Section {
                NavigationLink {
                    MonthPatternView()
                } label: {
                    Label("High-price months", systemImage: "chart.bar.xaxis")
                }
            } footer: {
                Text("When prices are usually high or low in each zone, with festival periods.")
            }
            ClarificationSection(text: store.clarification)
        }
        .refreshable {
            await store.refresh()
        }
        .navigationTitle("EggPaisa")
        .toolbar {
            Button("About", systemImage: "info.circle") {
                showsAbout = true
            }
        }
        .sheet(isPresented: $showsAbout) {
            NavigationStack {
                AboutView()
            }
            .environment(store)
        }
    }

    /// "Today, 27 Oct", "Yesterday, 26 Oct", or "Sat 24 Oct" for an older day.
    private static func dayText(_ date: Date) -> String {
        let today = PriceCalendar.today()
        let day = date.formatted(.dateTime.day().month(.abbreviated))
        if date == today {
            return String(localized: "Today, \(day)")
        }
        if date == PriceCalendar.day(-1, after: today) {
            return String(localized: "Yesterday, \(day)")
        }
        return date.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated))
    }
}

/// Whether the prices are today's, and when NECC was last checked.
private struct UpdateStatus: View {
    @Environment(PriceStore.self) private var store

    var body: some View {
        if store.isRefreshing {
            Text("Checking NECC for new prices…")
        } else if let refreshError = store.refreshError {
            Text("\(refreshError) Showing saved prices. Pull down to try again.")
        } else if let lastChecked = store.lastChecked {
            let time = lastChecked.formatted(date: .omitted, time: .shortened)
            if store.lastPriceDate == PriceCalendar.today() {
                Text("These are today's prices. Checked at \(time).")
            } else {
                Text("NECC hasn't published today's prices yet. Checked at \(time).")
            }
        }
    }
}

struct ZoneRow: View {
    let zone: Zone
    /// The newest price date across zones; a zone that is behind shows its own date.
    let newestDate: Date?

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(zone.name)
                    .font(.headline)
                if let latest = zone.latest, latest.date != newestDate {
                    Text("Price from \(latest.date, format: .dateTime.day().month(.abbreviated))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                if let latest = zone.latest {
                    Text(PriceFormat.rupees(latest.price))
                        .font(.title3.weight(.semibold))
                        .monospacedDigit()
                }
                ChangeLabel(change: zone.change)
                    .font(.caption)
            }
        }
        .alignmentGuide(.listRowSeparatorLeading) { $0[.leading] }
    }
}
