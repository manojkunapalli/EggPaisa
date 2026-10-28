import Foundation

/// One month's daily price sheet from the NECC website.
struct NECCSheet {
    let year: Int
    let month: Int
    /// Prices by zone name and day of the month; days NECC shows as "-" are left out.
    let prices: [String: [Int: Double]]
}

extension NECCSheet {
    enum ReadError: Error {
        case wrongMonth
        case unexpectedTable
    }

    /// Downloads one month's sheet the way NECC's own form asks for it.
    static func fetch(year: Int, month: Int, from url: URL) async throws -> NECCSheet {
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        let monthText = String(format: "%02d", month)
        request.httpBody = Data(
            "ddlMonth=\(monthText)&ddlYear=\(year)&rblReportType=DailyReport&btnReport=Get+Sheet".utf8
        )
        let (data, response) = try await URLSession.shared.data(for: request)
        // Latin-1 reads any bytes, should the page ever not be UTF-8; zone names and prices are plain ASCII.
        guard (response as? HTTPURLResponse)?.statusCode == 200,
              let html = String(bytes: data, encoding: .utf8) ?? String(bytes: data, encoding: .isoLatin1) else {
            throw URLError(.badServerResponse)
        }
        return try NECCSheet(html: html, year: year, month: month)
    }

    /// Reads the page like `Scripts/necc.py`; a month without a price table has no prices.
    init(html: String, year: Int, month: Int) throws {
        guard Self.selectedOption("ddlMonth", in: html) == month,
              Self.selectedOption("ddlYear", in: html) == year else {
            throw ReadError.wrongMonth
        }
        var prices: [String: [Int: Double]] = [:]
        let rows = Self.tableRows(in: html)
        if let header = rows.first {
            let dayCells = header.dropFirst().dropLast()
            guard header.first?.hasPrefix("Name Of Zone") == true, header.last == "Average", !dayCells.isEmpty,
                  Array(dayCells) == (1...dayCells.count).map(String.init) else {
                throw ReadError.unexpectedTable
            }
            // Other rows name a section, such as "Prevailing Prices".
            for cells in rows.dropFirst() where cells.count == header.count {
                var days = prices[cells[0], default: [:]]
                for (index, text) in cells.dropFirst().dropLast().enumerated() {
                    if let price = try Self.price(text) {
                        days[index + 1] = price
                    }
                }
                prices[cells[0]] = days
            }
        }
        self.init(year: year, month: month, prices: prices)
    }

    private static func price(_ text: String) throws -> Double? {
        if text.isEmpty || text == "-" {
            return nil
        }
        guard let price = Double(text.replacingOccurrences(of: ",", with: "")), price > 0, price < 10_000 else {
            throw ReadError.unexpectedTable
        }
        return price
    }

    /// The value of the dropdown option the page marks as selected, i.e. the month or year it shows.
    private static func selectedOption(_ name: String, in html: String) -> Int? {
        guard let select = html.range(of: "name=\"\(name)\"") else { return nil }
        let rest = html[select.upperBound...]
        let options = rest[..<(rest.range(of: "</select>")?.lowerBound ?? rest.endIndex)]
        guard let option = options.firstMatch(of: #/<option[^>]*selected[^>]*>/#),
              let value = option.output.firstMatch(of: #/value=["']?(\d+)/#) else { return nil }
        return Int(value.output.1)
    }

    /// Cell texts of each row of the table whose header starts with "Name Of Zone".
    private static func tableRows(in html: String) -> [[String]] {
        guard let header = html.range(of: "Name Of Zone"),
              let start = html.range(of: "<tr", options: .backwards, range: html.startIndex..<header.lowerBound)
        else { return [] }
        let rest = html[start.lowerBound...]
        let table = rest[..<(rest.range(of: "</table>")?.lowerBound ?? rest.endIndex)]
        return table.components(separatedBy: "<tr").dropFirst().map { row in
            row.matches(of: #/<t[dh][^>]*>(.*?)</t[dh]>/#.dotMatchesNewlines()).map { cellText($0.output.1) }
        }
    }

    private static func cellText(_ cell: Substring) -> String {
        cell.replacing(#/<[^>]*>/#, with: "")
            .replacingOccurrences(of: "&nbsp;", with: " ")
            .replacingOccurrences(of: "&amp;", with: "&")
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")
    }
}
