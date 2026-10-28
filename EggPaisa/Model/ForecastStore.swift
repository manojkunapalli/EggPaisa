import Foundation
import Observation

/// The 14-day forecast from the daily GitHub job, kept for offline use.
@Observable
final class ForecastStore {
    private(set) var forecast: ForecastFile?
    @ObservationIgnored private var lastChecked: Date?
    @ObservationIgnored private var refreshTask: Task<Void, Never>?

    private static let fileName = "forecast.json"

    init() {
        forecast = RemoteData.saved(Self.fileName).flatMap { try? JSONDecoder().decode(ForecastFile.self, from: $0) }
    }

    /// Downloads again unless that worked in the last few minutes.
    func refreshIfStale() async {
        if let lastChecked, Date.now.timeIntervalSince(lastChecked) < 10 * 60 {
            return
        }
        await refresh()
    }

    /// Downloads the newest forecast; if that fails, the saved one stays.
    func refresh() async {
        if let refreshTask {
            await refreshTask.value
            return
        }
        let task = Task { await download() }
        refreshTask = task
        await task.value
        refreshTask = nil
    }

    private func download() async {
        guard let data = try? await RemoteData.download(Self.fileName),
              let file = try? JSONDecoder().decode(ForecastFile.self, from: data) else { return }
        lastChecked = .now
        // Same-offset ISO 8601 times sort as text; a cached older copy never replaces a newer one.
        if file.generated > forecast?.generated ?? "" {
            forecast = file
            RemoteData.save(data, as: Self.fileName)
        }
    }
}
