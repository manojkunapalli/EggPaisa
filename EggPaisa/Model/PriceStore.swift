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
    /// When new prices were last read, from NECC or the daily job's copy.
    private(set) var lastChecked: Date?
    private(set) var refreshError: String?
    @ObservationIgnored private var file: PriceFile?
    @ObservationIgnored private var refreshTask: Task<Void, Never>?

    private static let savedPrices = "necc_prices.json"
    /// The daily GitHub job's copy of NECC's prices, used when NECC's site can't be read.
    private static let backupPrices = "prices.json"
    private static let monthPatternFile = "month_pattern.json"

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

    /// Adds NECC's newest prices, or the daily job's copy if NECC can't be read; else the prices shown stay.
    func refresh() async {
        if let refreshTask {
            await refreshTask.value
            return
        }
        let task = Task {
            await readNECC()
            await downloadMonthPatterns()
        }
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
            if await readBackup(of: file) {
                lastChecked = .now
                refreshError = nil
            } else {
                refreshError = Self.message(for: error)
            }
        }
    }

    /// Takes the daily job's copy if it is newer; `false` if it couldn't be read either.
    private func readBackup(of file: PriceFile) async -> Bool {
        guard let data = try? await RemoteData.download(Self.backupPrices),
              let backup = try? JSONDecoder().decode(PriceFile.self, from: data),
              backup.zones.map(\.id) == file.zones.map(\.id) else { return false }
        if backup.lastPriceDate > file.lastPriceDate {
            apply(backup)
            save(backup)
        }
        return true
    }

    /// The High-price months file, which the daily job rebuilds once a month.
    private func downloadMonthPatterns() async {
        guard let data = try? await RemoteData.download(Self.monthPatternFile),
              let patterns = try? JSONDecoder().decode(MonthPatternFile.self, from: data),
              let current = monthPatterns, Self.canReplace(current, with: patterns) else { return }
        monthPatterns = patterns
        RemoteData.save(data, as: Self.monthPatternFile)
    }

    private static func canReplace(_ current: MonthPatternFile, with other: MonthPatternFile) -> Bool {
        other.lastMonth >= current.lastMonth && other.zones.map(\.id) == current.zones.map(\.id)
    }

    private func loadPrices(from bundle: Bundle) {
        guard let url = bundle.url(forResource: "necc_prices", withExtension: "json") else {
            loadError = String(localized: "The price file is missing from the app.")
            return
        }
        do {
            let bundled = try JSONDecoder().decode(PriceFile.self, from: Data(contentsOf: url))
            // A saved copy is used only while it is newer than the prices this version of the app ships with.
            if let data = RemoteData.saved(Self.savedPrices),
               let saved = try? JSONDecoder().decode(PriceFile.self, from: data),
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
        if let data = try? JSONEncoder().encode(file) {
            RemoteData.save(data, as: Self.savedPrices)
        }
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
            let bundled = try JSONDecoder().decode(MonthPatternFile.self, from: Data(contentsOf: url))
            // A downloaded copy is used while it is at least as new as the bundled file.
            if let data = RemoteData.saved(Self.monthPatternFile),
               let saved = try? JSONDecoder().decode(MonthPatternFile.self, from: data),
               Self.canReplace(bundled, with: saved) {
                monthPatterns = saved
            } else {
                monthPatterns = bundled
            }
        } catch {
            monthPatternError = error.localizedDescription
        }
    }
}
