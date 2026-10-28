import Foundation

/// Files the daily GitHub job publishes, and the copies the app keeps for offline use.
enum RemoteData {
    /// GitHub Pages site of `.github/workflows/daily-forecast.yml`.
    static let siteURL = URL(string: "https://manojkunapalli.github.io/EggPaisa/")

    static func download(_ name: String) async throws -> Data {
        guard let url = siteURL?.appending(path: name) else {
            throw URLError(.badURL)
        }
        let request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    static func saved(_ name: String) -> Data? {
        try? Data(contentsOf: savedURL(name))
    }

    /// Best effort: without the saved copy, the next launch starts from the bundled files and downloads again.
    static func save(_ data: Data, as name: String) {
        let url = savedURL(name)
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try? data.write(to: url, options: .atomic)
    }

    private static func savedURL(_ name: String) -> URL {
        URL.applicationSupportDirectory.appending(path: name)
    }
}
