import Foundation
import Observation

@Observable
final class PriceStore {
    private(set) var zones: [Zone] = []
    private(set) var lastPriceDate: Date?
    private(set) var sourceURL: URL?
    private(set) var clarification = ""
    private(set) var loadError: String?
    private(set) var monthPatterns: MonthPatternFile?
    private(set) var monthPatternError: String?
    private(set) var isRefreshing = false
    /// When NECC's website was last read successfully.
    private(set) var lastChecked: Date?
    private(set) var refreshError: String?
    @ObservationIgnored private var file: PriceFile?
    @ObservationIgnored private var refreshTask: Task<Void, Never>?

    init(bundle: Bundle = .main) {
        loadPrices(from: bundle)
        loadMonthPatterns(from: bundle)
    }

    /// Reads NECC again unless that worked in the last few minutes.
    func refreshIfStale() async {
        if refreshError == nil, let lastChecked, Date.now.timeIntervalSince(lastChecked) < 10 * 60 {
            return
        }
        await refresh()
    }

    /// Adds NECC's newest prices; if that fails, the prices already shown stay.
    func refresh() async {
        if let refreshTask {
            await refreshTask.value
            return
        }
        let task = Task { await readNECC() }
        refreshTask = task
        await task.value
        refreshTask = nil
    }

    private func readNECC() async {
        guard let file else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        let today = PriceCalendar.today()
        do {
            var sheets: [NECCSheet] = []
            for (year, month) in Self.months(after: file.lastPriceDate, through: today) {
                do {
                    let sheet = try await NECCSheet.fetch(year: year, month: month, from: file.sourceURL)
                    sheets.append(sheet)
                } catch NECCSheet.ReadError.wrongMonth {
                    // On the 1st, NECC may not offer the new month or year yet; the other months still count.
                    continue
                }
            }
            guard file.zones.contains(where: { zone in sheets.contains { $0.prices[zone.neccName] != nil } }) else {
                throw NECCSheet.ReadError.unexpectedTable
            }
            let updated = file.merging(sheets, through: today)
            if updated != file {
                apply(updated)
                save(updated)
            }
            lastChecked = .now
            refreshError = nil
        } catch {
            refreshError = Self.message(for: error)
        }
    }

    private func loadPrices(from bundle: Bundle) {
        guard let url = bundle.url(forResource: "necc_prices", withExtension: "json") else {
            loadError = String(localized: "The price file is missing from the app.")
            return
        }
        do {
            let bundled = try JSONDecoder().decode(PriceFile.self, from: Data(contentsOf: url))
            // A saved copy is used only while it is newer than the prices this version of the app ships with.
            if let saved = try? JSONDecoder().decode(PriceFile.self, from: Data(contentsOf: Self.savedURL)),
               saved.lastPriceDate > bundled.lastPriceDate, saved.zones.map(\.id) == bundled.zones.map(\.id) {
                apply(saved)
            } else {
                apply(bundled)
            }
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func apply(_ file: PriceFile) {
        self.file = file
        zones = file.zones.compactMap { Zone(series: $0) }
        lastPriceDate = PriceCalendar.date(fromISODay: file.lastPriceDate)
        sourceURL = file.sourceURL
        clarification = file.clarification
    }

    private func save(_ file: PriceFile) {
        // Best effort: without the saved copy, the next launch starts from the bundled prices and reads NECC again.
        try? FileManager.default.createDirectory(
            at: Self.savedURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try? JSONEncoder().encode(file).write(to: Self.savedURL, options: .atomic)
    }

    private static var savedURL: URL {
        URL.applicationSupportDirectory.appending(path: "necc_prices.json")
    }

    /// From a week before the newest price, as NECC sometimes fills in days late, to this month; a year at most.
    private static func months(after lastPriceDate: String, through today: Date) -> [(year: Int, month: Int)] {
        let calendar = PriceCalendar.calendar
        let weekBefore = PriceCalendar.date(fromISODay: lastPriceDate).map { PriceCalendar.day(-7, after: $0) }
        let yearBefore = calendar.date(byAdding: .month, value: -11, to: today) ?? today
        let first = monthIndex(max(min(weekBefore ?? today, today), yearBefore))
        return (first...monthIndex(today)).map { (year: $0 / 12, month: $0 % 12 + 1) }
    }

    private static func monthIndex(_ date: Date) -> Int {
        let parts = PriceCalendar.calendar.dateComponents([.year, .month], from: date)
        return (parts.year ?? 0) * 12 + (parts.month ?? 1) - 1
    }

    private static func message(for error: Error) -> String {
        if (error as? URLError)?.code == .notConnectedToInternet {
            return String(localized: "You're offline.")
        }
        if error is NECCSheet.ReadError {
            return String(localized: "Couldn't read prices from NECC's website.")
        }
        return String(localized: "Couldn't reach NECC.")
    }

    private func loadMonthPatterns(from bundle: Bundle) {
        guard let url = bundle.url(forResource: "necc_month_pattern", withExtension: "json") else {
            monthPatternError = String(localized: "The high-price months file is missing from the app.")
            return
        }
        do {
            monthPatterns = try JSONDecoder().decode(MonthPatternFile.self, from: Data(contentsOf: url))
        } catch {
            monthPatternError = error.localizedDescription
        }
    }
}
